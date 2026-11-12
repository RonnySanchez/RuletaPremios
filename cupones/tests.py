from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from encuestas.models import Pais, Tienda

from .models import Cupon, PlantillaCuponPremio, PresentacionCupon, TipoDescuento
from .services import (
    calcular_descuento,
    calcular_vencimiento,
    renderizar_codigo,
    validar_formato_codigo,
)


@override_settings(TIME_ZONE="America/Lima", USE_TZ=True)
class GeneracionCodigoTests(SimpleTestCase):
    def test_renderiza_tienda_hora_y_digitos_aleatorios(self):
        tienda = SimpleNamespace(id_efsystem=Decimal("3"))
        fecha = timezone.make_aware(datetime(2026, 8, 4, 12, 50))

        with patch("cupones.services.secrets.choice", return_value="7"):
            codigo = renderizar_codigo("CUPON20-tt-hhmm-nnnn", tienda, fecha)

        self.assertEqual(codigo, "CUPON20-03-1250-7777")

    def test_rechaza_formato_con_menos_de_cuatro_digitos_aleatorios(self):
        with self.assertRaises(ValidationError):
            validar_formato_codigo("CUPON-tt-nnn")

    def test_rechaza_tokens_desconocidos(self):
        with self.assertRaises(ValidationError):
            validar_formato_codigo("CUPON-xx-nnnn")


@override_settings(TIME_ZONE="America/Lima", USE_TZ=True)
class VigenciaCuponTests(SimpleTestCase):
    def test_vigencia_por_dias_termina_al_final_del_ultimo_dia(self):
        inicio = timezone.make_aware(datetime(2026, 8, 4, 12, 30))
        plantilla = SimpleNamespace(
            tipo_vigencia=PlantillaCuponPremio.TipoVigencia.DIAS,
            dias_vigencia=3,
            fecha_vencimiento_fija=None,
        )

        vencimiento = timezone.localtime(calcular_vencimiento(plantilla, inicio))

        self.assertEqual(vencimiento.date(), date(2026, 8, 7))
        self.assertEqual((vencimiento.hour, vencimiento.minute, vencimiento.second), (23, 59, 59))

    def test_vigencia_fija_termina_al_final_de_la_fecha(self):
        inicio = timezone.make_aware(datetime(2026, 8, 4, 12, 30))
        plantilla = SimpleNamespace(
            tipo_vigencia=PlantillaCuponPremio.TipoVigencia.FECHA_FIJA,
            dias_vigencia=None,
            fecha_vencimiento_fija=date(2026, 8, 31),
        )

        vencimiento = timezone.localtime(calcular_vencimiento(plantilla, inicio))

        self.assertEqual(vencimiento.date(), date(2026, 8, 31))
        self.assertEqual((vencimiento.hour, vencimiento.minute), (23, 59))


class CalculoDescuentoTests(SimpleTestCase):
    def test_porcentaje_respeta_descuento_maximo(self):
        cupon = SimpleNamespace(
            tipo=TipoDescuento.PORCENTAJE,
            valor=Decimal("20"),
            minimo_compra=Decimal("100"),
            maximo_descuento=Decimal("30"),
        )

        self.assertEqual(calcular_descuento(cupon, Decimal("200")), Decimal("30.00"))

    def test_monto_fijo_no_supera_el_total(self):
        cupon = SimpleNamespace(
            tipo=TipoDescuento.MONTO,
            valor=Decimal("50"),
            minimo_compra=Decimal("0"),
            maximo_descuento=None,
        )

        self.assertEqual(calcular_descuento(cupon, Decimal("35")), Decimal("35.00"))


class CuponAPIV2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="efsystem-v2")
        pais = Pais.objects.create(nombre="Peru")
        Tienda.objects.create(nombre="Tienda 03", pais=pais, id_efsystem=3)
        Tienda.objects.create(nombre="Tienda 04", pais=pais, id_efsystem=4)
        cls.cupon = Cupon.objects.create(
            codigo="NAV30-PRUEBA", valor=30, cantidad_maxima_productos=1,
            vencimiento=timezone.now() + timedelta(days=1),
        )
        cls.cupon.presentaciones.add(
            PresentacionCupon.objects.create(nombre="Perfume 100 ml", codigo_efsystem="0100"),
        )

    def setUp(self):
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.usuario)}")
        self.consultar = reverse("api_v2_consultar_cupon", args=[self.cupon.codigo.lower()])
        self.validar = reverse("api_v2_validar_cupon")
        self.usar = reverse("api_v2_usar_cupon")
        self.datos = {
            "codigo": self.cupon.codigo, "tienda": "3", "nro_referencia": "VENTA-01",
            "monto_total": "220.00", "presentacion_codigo": "0100",
            "cantidad_productos": 1, "monto_aplicable": "160.00", "idempotency_key": "CANJE-01",
        }

    def test_consulta_v2_conserva_estructura_y_no_consume(self):
        respuesta = self.api.get(self.consultar)
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        anterior = self.api.get(reverse("api_consultar_cupon", args=[self.cupon.codigo]))
        self.assertEqual(anterior.status_code, 200)
        self.assertEqual(datos, anterior.json())
        self.assertEqual(datos["codigo"], self.cupon.codigo)
        self.assertEqual(datos["presentaciones"], [{"nombre": "Perfume 100 ml", "codigo_efsystem": "0100"}])
        self.assertEqual(datos["cantidad_maxima_productos"], 1)
        self.assertFalse(datos["requiere_identificacion"])
        self.assertTrue(datos["is_active"])
        self.assertEqual(datos["usos_actuales"], 0)
        self.assertFalse(self.cupon.usos.exists())

    def test_consulta_v2_devuelve_404_para_cupon_inexistente_o_agotado(self):
        desconocido = reverse("api_v2_consultar_cupon", args=["NO-EXISTE"])
        self.assertEqual(self.api.get(desconocido).status_code, 404)
        self.assertEqual(self.api.post(self.usar, self.datos, format="json").status_code, 200)
        self.assertEqual(self.api.get(self.consultar).status_code, 404)

    def test_v2_requiere_autenticacion_en_las_tres_rutas(self):
        anonimo = APIClient()
        self.assertEqual(anonimo.get(self.consultar).status_code, 401)
        for url in (self.validar, self.usar):
            with self.subTest(url=url):
                self.assertEqual(anonimo.post(url, self.datos, format="json").status_code, 401)

    def test_validacion_y_canje_con_descuento_confirmado(self):
        validacion = self.api.post(self.validar, self.datos, format="json")
        self.assertEqual(validacion.status_code, 200)
        self.assertEqual(validacion.json()["descuento_calculado"], "48.00")
        self.assertFalse(self.cupon.usos.exists())
        respuesta = self.api.post(self.usar, {**self.datos, "monto_descuento": "48.00"}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.json()), {"mensaje", "datos_registrados"})
        registro = respuesta.json()["datos_registrados"]
        self.assertEqual(registro["nro_referencia"], "VENTA-01")
        self.assertEqual(registro["monto_descuento"], "48.00")
        self.assertEqual(registro["monto_aplicable"], "160.00")
        self.assertEqual(registro["presentacion_codigo"], "0100")
        self.assertEqual(self.cupon.usos.get().monto_descuento, Decimal("48.00"))

    def test_descuento_distinto_no_consume_ni_reserva_la_clave(self):
        respuesta = self.api.post(self.usar, {**self.datos, "monto_descuento": "66.00"}, format="json")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.json()["descuento_calculado"], "48.00")
        self.cupon.refresh_from_db()
        self.assertEqual(self.cupon.usos_actuales, 0)
        self.assertFalse(self.cupon.usos.exists())
        self.assertEqual(self.api.post(self.usar, self.datos, format="json").status_code, 200)

    def test_reintento_equivalente_devuelve_el_mismo_registro_incluso_vencido(self):
        inicial = self.api.post(self.usar, self.datos, format="json")
        self.assertEqual(inicial.status_code, 200)
        reintento = {**self.datos, "codigo": self.cupon.codigo.lower(), "tienda": 3, "monto_descuento": "48"}
        # El cupón y el JWT tienen vigencias independientes.
        Cupon.objects.filter(pk=self.cupon.pk).update(vencimiento=timezone.now() - timedelta(seconds=1))
        respuesta = self.api.post(self.usar, reintento, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), inicial.json())
        self.assertEqual(self.cupon.usos.count(), 1)

    def test_misma_clave_con_datos_distintos_devuelve_conflicto(self):
        self.assertEqual(self.api.post(self.usar, self.datos, format="json").status_code, 200)
        cambios = {
            "codigo": "OTRO-CUPON", "tienda": "4", "nro_referencia": "VENTA-02",
            "monto_total": "221.00", "monto_aplicable": "159.00", "cantidad_productos": 2,
            "presentacion_codigo": "0050", "categoria": "Otra",
            "tipo_identificacion": "DNI", "numero_identificacion": "12345678",
            "monto_descuento": "47.00",
        }
        for campo, valor in cambios.items():
            with self.subTest(campo=campo):
                respuesta = self.api.post(self.usar, {**self.datos, campo: valor}, format="json")
                self.assertEqual(respuesta.status_code, 409)
                self.assertNotIn("datos_registrados", respuesta.json())
        self.cupon.refresh_from_db()
        self.assertEqual(self.cupon.usos_actuales, 1)
        self.assertEqual(self.cupon.usos.count(), 1)

    def test_otra_credencial_no_puede_recuperar_un_canje_ajeno(self):
        self.assertEqual(self.api.post(self.usar, self.datos, format="json").status_code, 200)
        otro = get_user_model().objects.create_user(username="otra-credencial")
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(otro)}")
        respuesta = self.api.post(self.usar, self.datos, format="json")
        self.assertEqual(respuesta.status_code, 409)
        self.assertNotIn("datos_registrados", respuesta.json())

    def test_uso_anterior_conserva_sus_campos_y_no_pide_clave(self):
        cupon = Cupon.objects.create(codigo="CUPON-ANTERIOR", valor=30, vencimiento=self.cupon.vencimiento)
        datos = {
            "codigo": cupon.codigo, "tienda": 3, "nro_referencia": "VENTA-ANTERIOR",
            "monto_total": "100.00", "monto_descuento": "30.00",
        }
        respuesta = self.api.post(reverse("api_usar_cupon"), datos, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.json()), {"mensaje", "datos_registrados"})
        self.assertEqual(respuesta.json()["datos_registrados"]["monto_descuento"], "30.00")
        self.assertIsNone(cupon.usos.get().idempotency_key)


class CanjeAPIV2ConcurrenteTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_dos_cajas_no_pueden_canjear_el_mismo_cupon(self):
        usuario = get_user_model().objects.create_user(username="cajas-v2")
        pais = Pais.objects.create(nombre="Peru")
        Tienda.objects.create(nombre="Tienda 03", pais=pais, id_efsystem=3)
        cupon = Cupon.objects.create(
            codigo="CANJE-CONCURRENTE", valor=30, vencimiento=timezone.now() + timedelta(days=1),
        )
        url = reverse("api_v2_usar_cupon")
        barrera = Barrier(2)

        def canjear(referencia):
            try:
                api = APIClient()
                api.force_authenticate(usuario)
                barrera.wait(timeout=10)
                return api.post(url, {
                    "codigo": cupon.codigo, "tienda": 3, "monto_total": "100.00",
                    "nro_referencia": referencia, "idempotency_key": referencia,
                }, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            futuros = [ejecutor.submit(canjear, referencia) for referencia in ("CAJA-1", "CAJA-2")]
            self.assertCountEqual([futuro.result(timeout=20) for futuro in futuros], [200, 400])
        cupon.refresh_from_db()
        self.assertEqual(cupon.usos_actuales, 1)
        self.assertEqual(cupon.usos.count(), 1)
