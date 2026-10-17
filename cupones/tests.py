from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from .models import PlantillaCuponPremio, TipoDescuento
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
