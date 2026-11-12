import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from cupones.models import Cupon, PlantillaCuponPremio, PresentacionCupon
from .forms import ContactoCuponForm, EncuestaFijaForm
from .models import (
    EncuestaFija, EncuestaFijaPremio, EncuestaFijaRespuesta,
    FormularioEncFija, Pais, Premio, Region, TicketConsulta, Tienda, ParticipacionCuponDirecto, TemaRuleta,
    TiendaPremio, TicketVentasEnLinea,
)
from .services import entregar_premio_directo, resolver_campana


@override_settings(TIME_ZONE='America/Lima', USE_TZ=True)
class CampanaCuponTests(TestCase):
    def setUp(self):
        self.ahora = timezone.make_aware(datetime(2026, 12, 20, 12))
        self.reloj = patch('django.utils.timezone.now', return_value=self.ahora)
        self.reloj.start()
        self.addCleanup(self.reloj.stop)
        self.pais = Pais.objects.create(nombre='Peru')
        self.region = Region.objects.create(nombre='Lima', pais=self.pais)
        self.tienda = Tienda.objects.create(nombre='Tienda 03', pais=self.pais, region=self.region, id_efsystem=3, monto_minimo_promociones=150)
        self.premio = Premio.objects.create(nombre='Cupon transferible 30%')
        self.plantilla = PlantillaCuponPremio.objects.create(
            premio=self.premio, valor=30, tipo_vigencia='FECHA_FIJA',
            fecha_inicio_fija=datetime(2027, 1, 1).date(),
            fecha_vencimiento_fija=datetime(2027, 1, 31).date(),
            formato_codigo='NAV30-tt-nnnnnnnnnn', transferible=True, cantidad_maxima_productos=1,
        )
        self.presentacion = PresentacionCupon.objects.create(nombre='Perfume 100 ml', codigo_efsystem='TEST-P100')
        self.plantilla.presentaciones.add(self.presentacion)
        self.formulario = FormularioEncFija.objects.create(nombre='Contacto', codigo='CONTACTO_CUPON')
        self.campana = EncuestaFija.objects.create(
            titulo='Navidad', descripcion='Tu compra tiene cupon', tipo_juego='DIRECTO',
            encuestafija=self.formulario, premio_directo=self.premio,
            inicio_campana=self.ahora - timedelta(days=10), fin_campana=self.ahora + timedelta(days=10),
        )
        self.campana.tiendas.add(self.tienda)
        self.datos = {'nombre': 'Ana', 'apellidos': 'Perez', 'telefono': '987654321', 'correo': 'ana@example.com', 'acepPolPriv': True, 'acepProm': False}
        self.ticket = self.crear_ticket()
        self.api = APIClient()
        self.api.force_authenticate(get_user_model().objects.create_user(username='efsystem'))

    def crear_ticket(self, codigo='T-01', monto='150.00'):
        return TicketConsulta.objects.create(
            tienda=self.tienda, codigo=codigo, monto=monto,
            encuesta_id_resuelta=str(self.campana.pk), status_respuesta=200,
            token_participacion=uuid.uuid4(),
        )

    def emitir(self):
        return entregar_premio_directo(self.campana, self.tienda, self.ticket, self.datos)

    def test_emite_sin_stock_transferible_y_sin_datos_ficticios(self):
        premio = self.emitir()
        cupon = premio.cupon
        self.assertEqual(cupon.valor, Decimal('30'))
        self.assertTrue(cupon.transferible)
        self.assertIsNone(cupon.numero_identificacion)
        self.assertEqual(cupon.limite_usos, 1)
        self.assertEqual(cupon.minimo_compra, 0)
        self.assertIsNone(cupon.maximo_descuento)
        self.assertEqual(cupon.categorias.count(), 0)
        self.assertEqual(cupon.presentaciones.count(), 1)
        self.assertEqual(cupon.cantidad_maxima_productos, 1)
        self.assertIsNone(premio.respuesta.fnac)
        self.assertIsNone(premio.respuesta.valoracion_producto)
        self.assertEqual(premio.respuesta.DNI, '')
        self.assertFalse(premio.respuesta.acepProm)
        self.assertEqual(timezone.localtime(cupon.inicio), timezone.make_aware(datetime(2027, 1, 1)))
        self.assertEqual(timezone.localtime(cupon.vencimiento).date(), datetime(2027, 1, 31).date())
        self.assertEqual(cupon.emitido_en, self.ahora)
        self.assertFalse(cupon.is_active)

    def test_monto_inferior_no_emite(self):
        self.ticket.monto = Decimal('149.99')
        self.ticket.save()
        with self.assertRaises(ValidationError):
            self.emitir()
        self.assertEqual(Cupon.objects.count(), 0)

    def test_monto_superior_emite(self):
        self.ticket.monto = Decimal('150.01')
        self.assertIsNotNone(self.emitir().cupon)

    def test_repetir_entrega_devuelve_el_mismo_cupon(self):
        primero = self.emitir()
        self.assertEqual(self.emitir().pk, primero.pk)
        self.assertEqual(EncuestaFijaRespuesta.objects.count(), 1)
        self.assertEqual(EncuestaFijaPremio.objects.count(), 1)
        self.assertEqual(Cupon.objects.count(), 1)

    def test_reversion_si_falla_la_emision(self):
        with patch('encuestas.services.emitir_cupon_para_premio', side_effect=ValidationError('Fallo de emision')):
            with self.assertRaises(ValidationError):
                self.emitir()
        self.assertEqual(EncuestaFijaRespuesta.objects.count(), 0)
        self.assertEqual(EncuestaFijaPremio.objects.count(), 0)

    def test_campana_fuera_de_fecha_no_emite(self):
        with patch('django.utils.timezone.now', return_value=self.ahora + timedelta(days=11)):
            with self.assertRaises(ValidationError):
                self.emitir()

    def test_ticket_de_otra_campana_no_emite(self):
        self.ticket.encuesta_id_resuelta = '999'
        with self.assertRaises(ValidationError):
            self.emitir()

    def test_sin_consentimiento_no_emite(self):
        self.datos['acepPolPriv'] = False
        with self.assertRaises(ValidationError):
            self.emitir()

    def test_formulario_corto_y_validacion_anterior(self):
        self.assertTrue(ContactoCuponForm(self.datos).is_valid())
        self.assertFalse(EncuestaFijaForm(self.datos).is_valid())
        self.assertFalse(ContactoCuponForm({**self.datos, 'telefono': '123'}).is_valid())
        self.assertFalse(ContactoCuponForm({**self.datos, 'correo': 'sin-arroba'}).is_valid())

    def test_recorrido_http_y_recuperacion(self):
        url = reverse('contacto_cupon', args=[self.ticket.token_participacion])
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'contacto_cupon.html')
        self.assertContains(respuesta, 'Recibir mi cupón')
        envio = self.client.post(url, {**self.datos, 'codigo_ticket': 'ALTERADO', 'monto': 100000})
        self.assertEqual(envio.status_code, 302)
        self.assertEqual(EncuestaFijaRespuesta.objects.get().codigo_ticket, self.ticket.codigo)
        resultado = self.client.get(envio.url)
        self.assertContains(resultado, Cupon.objects.get().codigo)
        self.assertContains(resultado, '01/01/2027')
        self.assertEqual(resultado['Cache-Control'], 'private, no-store')
        self.assertEqual(self.client.post(url, self.datos).url, envio.url)
        with patch('django.utils.timezone.now', return_value=self.ahora + timedelta(days=40)):
            self.assertEqual(self.client.get(url).url, envio.url)

    def test_token_desconocido_y_ruta_legacy_no_exponen_cupon(self):
        premio = self.emitir()
        self.assertEqual(self.client.get(reverse('resultado_cupon', args=[uuid.uuid4()])).status_code, 404)
        respuesta = self.client.post(reverse('guardar_premio'), {'codigo_ticket': self.ticket.codigo})
        self.assertEqual(respuesta.status_code, 403)
        self.assertNotContains(respuesta, premio.cupon.codigo, status_code=403)
        self.assertEqual(self.client.post(reverse('ejecutar_sorteo_ajax'), {'codigo_ticket': self.ticket.codigo, 'tienda_id': self.tienda.pk, 'encuesta_id': self.campana.pk}).status_code, 400)

    def test_formulario_csrf_acepta_post_del_mismo_origen(self):
        cliente = Client(enforce_csrf_checks=True)
        url = reverse('contacto_cupon', args=[self.ticket.token_participacion])
        formulario = cliente.get(url)
        self.assertEqual(formulario['Referrer-Policy'], 'same-origin')
        datos = {**self.datos, 'csrfmiddlewaretoken': cliente.cookies['csrftoken'].value}
        respuesta = cliente.post(url, datos, HTTP_ORIGIN='http://testserver')
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Cupon.objects.count(), 1)

    def test_pantallas_cupon_aplican_y_actualizan_el_tema_de_campana(self):
        tema = TemaRuleta.objects.create(
            nombre='Tema de prueba de cupon', fondo_ruleta='#eff6ed', fondo_premio='#f7edf2',
            texto_principal='#172b22', texto_secundario='#40534a', segmento_5='#b32348',
            imagen_encabezado_ruleta='static/images/gira y gana.png',
            imagen_encabezado_premio='static/images/felicidades1.png',
            imagen_fondo_ruleta='static/img/fondoruleta.png',
        )
        self.campana.tema_ruleta = tema
        self.campana.save(update_fields=['tema_ruleta'])
        url_formulario = reverse('contacto_cupon', args=[self.ticket.token_participacion])
        formulario = self.client.get(url_formulario)
        self.assertEqual(formulario.context['ruleta_theme_vars'], tema.css_variables())
        self.assertContains(formulario, 'ruleta-theme ruleta-page cupon-contacto-page')
        self.assertContains(formulario, 'class="ruleta-header-banner"')
        self.assertContains(formulario, '--ruleta-bg-color: #eff6ed;')
        premio = self.emitir()
        url_resultado = reverse('resultado_cupon', args=[premio.token_resultado])
        resultado = self.client.get(url_resultado)
        self.assertEqual(resultado.context['ruleta_theme_vars'], tema.css_variables())
        self.assertContains(resultado, 'ruleta-theme premio-page cupon-resultado-page')
        self.assertContains(resultado, 'class="premio-header-banner"')
        self.assertContains(resultado, '--premio-bg-color: #f7edf2;')
        for respuesta in [formulario, resultado]:
            self.assertContains(respuesta, 'css/ruleta.css')
            self.assertContains(respuesta, 'css/cupon_directo.css')
            self.assertContains(respuesta, '--ef-text: #172b22;')
        tema.texto_principal = '#101010'
        tema.fondo_premio = '#ffffff'
        tema.save(update_fields=['texto_principal', 'fondo_premio'])
        otro_ticket = self.crear_ticket(codigo='TEMA-02')
        otro_formulario = reverse('contacto_cupon', args=[otro_ticket.token_participacion])
        self.assertContains(self.client.get(otro_formulario), '--ef-text: #101010;')
        self.assertContains(self.client.get(url_resultado), '--premio-bg-color: #ffffff;')

    def test_pantallas_cupon_sin_tema_usan_los_valores_predeterminados(self):
        formulario = self.client.get(reverse('contacto_cupon', args=[self.ticket.token_participacion]))
        premio = self.emitir()
        resultado = self.client.get(reverse('resultado_cupon', args=[premio.token_resultado]))
        for respuesta in [formulario, resultado]:
            self.assertEqual(respuesta.context['ruleta_theme_vars'], TemaRuleta.default_css_variables())
            self.assertContains(respuesta, '--ef-text: #eeeeee;')

    def test_avisos_cupon_conservan_tema_y_codigos_http(self):
        tema = TemaRuleta.objects.create(nombre='Avisos de cupon', fondo_sin_premio='#efedfa')
        self.campana.tema_ruleta = tema
        self.campana.save(update_fields=['tema_ruleta'])
        urls = [
            reverse('fijaConTicket', args=[self.tienda.pk, self.campana.pk, self.ticket.codigo]),
            reverse('ruleta', args=[self.campana.pk, self.tienda.pk, self.ticket.codigo]),
        ]
        for url in urls:
            respuesta = self.client.get(url)
            self.assertTemplateUsed(respuesta, 'RespEmitida.html')
            self.assertEqual(respuesta.context['ruleta_theme_vars'], tema.css_variables())
        with patch('django.utils.timezone.now', return_value=self.ahora + timedelta(days=11)):
            respuesta = self.client.get(reverse('contacto_cupon', args=[self.ticket.token_participacion]))
        self.assertContains(respuesta, '--sin-premio-bg-color: #efedfa;', status_code=400)
        premio = self.emitir()
        respuesta = self.client.post(reverse('guardar_premio'), {'codigo_ticket': self.ticket.codigo})
        self.assertContains(respuesta, '--sin-premio-bg-color: #efedfa;', status_code=403)
        self.assertNotContains(respuesta, premio.cupon.codigo, status_code=403)

    def test_formulario_csrf_rechaza_origen_ajeno_nulo_y_token_ausente(self):
        cliente = Client(enforce_csrf_checks=True)
        url = reverse('contacto_cupon', args=[self.ticket.token_participacion])
        cliente.get(url)
        datos = {**self.datos, 'csrfmiddlewaretoken': cliente.cookies['csrftoken'].value}
        for origen in ['null', 'http://sitio-ajeno.example']:
            with self.subTest(origen=origen):
                self.assertEqual(cliente.post(url, datos, HTTP_ORIGIN=origen).status_code, 403)
        self.assertEqual(cliente.post(url, self.datos, HTTP_ORIGIN='http://testserver').status_code, 403)
        self.assertEqual(Cupon.objects.count(), 0)

    def test_formulario_csrf_https_acepta_referer_del_mismo_sitio(self):
        cliente = Client(enforce_csrf_checks=True)
        url = reverse('contacto_cupon', args=[self.ticket.token_participacion])
        cliente.get(url, secure=True)
        datos = {**self.datos, 'csrfmiddlewaretoken': cliente.cookies['csrftoken'].value}
        respuesta = cliente.post(url, datos, secure=True, HTTP_REFERER='https://testserver' + url)
        self.assertEqual(respuesta.status_code, 302)

    def test_api_generacion_enlace_y_monto_minimo(self):
        for monto, status in [('149.99', 2), ('150.00', 200), ('150.01', 200)]:
            respuesta = self.api.post(reverse('encuesta-tienda'), {'tienda_id': 3, 'codigo': 'API-' + monto, 'monto': monto}, format='json')
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.json()['status'], status)
            self.assertEqual(set(respuesta.json()), {'Resp', 'status', 'encabezado', 'texto', 'codigo'})
            if status == 200:
                self.assertTrue(respuesta.json()['Resp'].startswith('http://testserver/polls/contacto/'))
                self.assertEqual(self.client.get(respuesta.json()['Resp']).status_code, 200)

    def test_api_rechaza_montos_invalidos(self):
        for monto in ['NaN', '-1', 'infinity', 'texto', '150.001']:
            self.assertEqual(self.api.post(reverse('encuesta-tienda'), {'tienda_id': 3, 'codigo': 'BAD', 'monto': monto}, format='json').status_code, 400)

    def test_resuelve_region_pais_y_rechaza_ambiguedad(self):
        self.assertEqual(resolver_campana(self.tienda), self.campana)
        otra = EncuestaFija.objects.create(titulo='Otra', descripcion='Otra', region=self.region)
        with self.assertRaises(ValidationError):
            resolver_campana(self.tienda)
        self.campana.activa = False
        self.campana.save()
        self.assertEqual(resolver_campana(self.tienda), otra)
        otra.region = None
        otra.pais = self.pais
        otra.save()
        self.assertEqual(resolver_campana(self.tienda), otra)

    def test_restriccion_db_impide_otra_participacion_del_ticket(self):
        self.emitir()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParticipacionCuponDirecto.objects.create(encuesta_fija=self.campana, tienda=self.tienda, codigo_ticket=self.ticket.codigo)

    def test_canje_solo_en_enero_y_uso_unico_sin_identificacion(self):
        cupon = self.emitir().cupon
        datos = {'codigo': cupon.codigo, 'tienda': 3, 'monto_total': '10.00', 'monto_aplicable': '10.00', 'cantidad_productos': 1, 'presentacion_codigo': self.presentacion.codigo_efsystem}
        validar = reverse('api_v2_validar_cupon')
        usar = reverse('api_v2_usar_cupon')
        self.assertEqual(self.api.post(validar, datos, format='json').status_code, 400)
        for fecha in [datetime(2027, 1, 1), datetime(2027, 1, 31, 23, 59, 59)]:
            with patch('django.utils.timezone.now', return_value=timezone.make_aware(fecha)):
                respuesta = self.api.post(validar, datos, format='json')
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.json()['descuento_calculado'], '3.00')
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2027, 2, 1))):
            self.assertEqual(self.api.post(validar, datos, format='json').status_code, 400)
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2027, 1, 10))):
            datos['idempotency_key'] = 'VENTA-ENERO-01'
            self.assertEqual(self.api.post(usar, datos, format='json').status_code, 200)
            self.assertEqual(self.api.post(usar, datos, format='json').status_code, 200)
            datos['idempotency_key'] = 'OTRA-VENTA'
            self.assertEqual(self.api.post(usar, datos, format='json').status_code, 400)

    def test_api_legacy_conserva_ruta_y_encuesta_anterior(self):
        self.campana.tipo_juego = 'RULETA'
        self.campana.encuestafija = None
        self.campana.save()
        respuesta = self.api.post(reverse('encuesta-tienda'), {'tienda_id': 3, 'codigo': 'LEGACY-01', 'monto': '150.00'}, format='json')
        self.assertEqual(respuesta.json()['status'], 200)
        self.assertIn('/polls/fija/', respuesta.json()['Resp'])

    def test_plantilla_inactiva_y_contacto_no_transferible_se_rechazan(self):
        self.plantilla.activo = False
        self.plantilla.save()
        with self.assertRaises(ValidationError):
            self.emitir()
        self.plantilla.activo = True
        self.plantilla.transferible = False
        self.plantilla.save()
        with self.assertRaises(ValidationError):
            self.emitir()

    def test_consulta_legacy_rechaza_cupon_antes_de_enero(self):
        cupon = self.emitir().cupon
        respuesta = self.api.get(reverse('api_consultar_cupon', args=[cupon.codigo]))
        self.assertEqual(respuesta.status_code, 404)
        datos = {'codigo': cupon.codigo, 'tienda': 3, 'monto_total': '10.00', 'monto_descuento': '3.00'}
        self.assertEqual(self.api.post(reverse('api_usar_cupon'), datos, format='json').status_code, 400)

    def test_descuento_solo_sobre_un_perfume_del_ticket(self):
        cupon = self.emitir().cupon
        datos = {'codigo': cupon.codigo, 'tienda': 3, 'monto_total': '300.00', 'monto_aplicable': '180.00', 'cantidad_productos': 1, 'presentacion_codigo': self.presentacion.codigo_efsystem}
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2027, 1, 10))):
            respuesta = self.api.post(reverse('api_v2_validar_cupon'), datos, format='json')
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.json()['descuento_calculado'], '54.00')
            datos['idempotency_key'] = 'PERFUME-UNICO'
            self.assertEqual(self.api.post(reverse('api_v2_usar_cupon'), datos, format='json').status_code, 200)
        uso = cupon.usos.get()
        self.assertEqual(uso.monto_total, Decimal('300.00'))
        self.assertEqual(uso.monto_aplicable, Decimal('180.00'))
        self.assertEqual(uso.cantidad_productos, 1)
        self.assertEqual(uso.monto_descuento, Decimal('54.00'))

    def test_rechaza_presentacion_cantidad_o_importe_incorrectos(self):
        cupon = self.emitir().cupon
        datos = {'codigo': cupon.codigo, 'tienda': 3, 'monto_total': '300.00', 'monto_aplicable': '180.00', 'cantidad_productos': 1, 'presentacion_codigo': self.presentacion.codigo_efsystem}
        variaciones = [
            {'presentacion_codigo': 'TEST-P50'}, {'presentacion_codigo': None},
            {'cantidad_productos': 2}, {'cantidad_productos': 0},
            {'cantidad_productos': 1.5}, {'monto_aplicable': '301.00'},
        ]
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2027, 1, 10))):
            for cambios in variaciones:
                with self.subTest(cambios=cambios):
                    payload = {**datos, **cambios, 'idempotency_key': str(uuid.uuid4())}
                    for ruta in ['api_v2_validar_cupon', 'api_v2_usar_cupon']:
                        self.assertEqual(self.api.post(reverse(ruta), payload, format='json').status_code, 400)
            for campo in ['cantidad_productos', 'monto_aplicable']:
                payload = dict(datos)
                del payload[campo]
                self.assertEqual(self.api.post(reverse('api_v2_validar_cupon'), payload, format='json').status_code, 400)
        self.assertEqual(cupon.usos.count(), 0)
        cupon.refresh_from_db()
        self.assertEqual(cupon.usos_actuales, 0)

    def test_canje_legacy_no_evade_restriccion_de_presentacion(self):
        cupon = self.emitir().cupon
        datos = {'codigo': cupon.codigo, 'tienda': 3, 'monto_total': '300.00', 'monto_descuento': '90.00'}
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2027, 1, 10))):
            self.assertEqual(self.api.post(reverse('api_usar_cupon'), datos, format='json').status_code, 400)
        self.assertEqual(cupon.usos.count(), 0)

    def test_limite_de_productos_se_copia_al_cupon_emitido(self):
        cupon = self.emitir().cupon
        self.plantilla.cantidad_maxima_productos = 2
        self.plantilla.save()
        self.plantilla.presentaciones.clear()
        cupon.refresh_from_db()
        self.assertEqual(cupon.cantidad_maxima_productos, 1)
        self.assertEqual(cupon.presentaciones.get(), self.presentacion)


@override_settings(TIME_ZONE='America/Lima', USE_TZ=True)
class TemaEncuestaTests(TestCase):
    def setUp(self):
        pais = Pais.objects.create(nombre='Peru')
        self.tienda = Tienda.objects.create(nombre='Tienda de resenas', pais=pais)
        self.tema = TemaRuleta.objects.create(
            nombre='Tema de resenas', fondo_ruleta='#eff6ed', fondo_sin_premio='#f7edf2',
            texto_principal='#172b22', texto_secundario='#40534a', segmento_4='#4e715b',
            imagen_encabezado_ruleta='static/images/felicidades1.png',
        )
        self.campana = EncuestaFija.objects.create(titulo='Resena', descripcion='Tu experiencia', tema_ruleta=self.tema)
        self.campana.tiendas.add(self.tienda)
        self.premio = Premio.objects.create(nombre='Premio de prueba')
        self.stock = TiendaPremio.objects.create(tienda=self.tienda, premio=self.premio, cantidad=5, visible=True)
        self.url = reverse('fijaConTicket', args=[self.tienda.pk, self.campana.pk, 'RESENA-01'])
        self.datos = {
            'codigo_ticket': 'RESENA-01', 'nombre': 'Ana', 'apellidos': 'Perez',
            'telefono': '987654321', 'correo': 'ana@example.com', 'fnac': '01/01/1990',
            'tipo_identificacion': 'DNI', 'DNI': '12345678', 'acepPolPriv': True,
            'valoracion_producto': '5', 'valoracion_atencion': '4', 'probabilidad_recomendacion': '5',
        }

    def comprobar_aviso(self, respuesta):
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, 'RespEmitida.html')
        self.assertEqual(respuesta.context['ruleta_theme_vars'], self.tema.css_variables())
        self.assertContains(respuesta, 'ruleta-theme sin-premio-page aviso-page')
        self.assertContains(respuesta, '--sin-premio-bg-color: #f7edf2;')
        self.assertContains(respuesta, 'css/encuesta.css')

    def crear_respuesta(self):
        return EncuestaFijaRespuesta.objects.create(
            encuesta_fija=self.campana, tienda=self.tienda, codigo_ticket='RESENA-01',
            nombre='Ana', apellidos='Perez', telefono='987654321', correo='ana@example.com',
            DNI='12345678', acepPolPriv=True,
        )

    def crear_premio(self, respuesta):
        return EncuestaFijaPremio.objects.create(
            encuesta_fija=self.campana, tienda=self.tienda, respuesta=respuesta,
            codigo_ticket=respuesta.codigo_ticket, nombre='Ana', apellidos='Perez', premio=self.premio,
        )

    def test_encuesta_aplica_y_actualiza_el_tema(self):
        respuesta = self.client.get(self.url)
        self.assertTemplateUsed(respuesta, 'poll_f1.html')
        self.assertEqual(respuesta.context['ruleta_theme_vars'], self.tema.css_variables())
        self.assertContains(respuesta, 'ruleta-theme ruleta-page encuesta-page')
        self.assertContains(respuesta, 'css/encuesta.css')
        self.assertContains(respuesta, '--ruleta-bg-color: #eff6ed;')
        self.assertContains(respuesta, 'class="ruleta-header-banner"')
        self.tema.texto_principal = '#234567'
        self.tema.save(update_fields=['texto_principal'])
        self.assertContains(self.client.get(self.url), '--ef-text: #234567;')

    def test_encuesta_con_errores_conserva_tema_y_datos(self):
        respuesta = self.client.post(self.url, {**self.datos, 'correo': 'invalido'})
        self.assertTemplateUsed(respuesta, 'poll_f1.html')
        self.assertEqual(respuesta.context['ruleta_theme_vars'], self.tema.css_variables())
        self.assertTrue(respuesta.context['form'].errors)
        self.assertContains(respuesta, 'value="Ana"')
        self.assertEqual(EncuestaFijaRespuesta.objects.count(), 0)

    def test_encuesta_valida_conserva_el_guardado_y_redireccion(self):
        respuesta = self.client.post(self.url, self.datos)
        self.assertRedirects(respuesta, reverse('ruleta', args=[self.campana.pk, self.tienda.pk, 'RESENA-01']), fetch_redirect_response=False)
        self.assertEqual(EncuestaFijaRespuesta.objects.get().valoracion_atencion, 4)

    def test_avisos_por_tienda_no_asignada_y_sin_stock(self):
        self.campana.tiendas.clear()
        for url in [self.url, reverse('fija', args=[self.tienda.pk, self.campana.pk])]:
            self.comprobar_aviso(self.client.get(url))
        self.campana.tiendas.add(self.tienda)
        self.stock.cantidad = 0
        self.stock.save()
        self.comprobar_aviso(self.client.get(self.url))

    def test_aviso_por_ticket_invalido_y_vencido(self):
        self.tienda.requiere_validacion_ticket = True
        self.tienda.save(update_fields=['requiere_validacion_ticket'])
        self.comprobar_aviso(self.client.get(self.url))
        TicketVentasEnLinea.objects.create(
            nro_ticket='RESENA-01', tienda=self.tienda, encuesta_fija=self.campana,
            vigencia=timezone.now() - timedelta(days=1),
        )
        self.comprobar_aviso(self.client.get(self.url))

    def test_avisos_por_participacion_previa_en_encuesta_ruleta_y_cajas(self):
        respuesta = self.crear_respuesta()
        self.crear_premio(respuesta)
        urls = [
            self.url,
            reverse('ruleta', args=[self.campana.pk, self.tienda.pk, 'RESENA-01']),
            reverse('juego_regalos', args=[self.campana.pk, self.tienda.pk, 'RESENA-01']),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.comprobar_aviso(self.client.get(url))
        self.tienda.requiere_validacion_ticket = True
        self.tienda.save(update_fields=['requiere_validacion_ticket'])
        TicketVentasEnLinea.objects.create(
            nro_ticket='RESENA-01', tienda=self.tienda, encuesta_fija=self.campana,
            utilizado=True, vigencia=timezone.now() + timedelta(days=1),
        )
        self.comprobar_aviso(self.client.get(self.url))

    def test_avisos_de_ruleta_sin_respuesta_y_sin_stock(self):
        url = reverse('ruleta', args=[self.campana.pk, self.tienda.pk, 'RESENA-01'])
        self.comprobar_aviso(self.client.get(url))
        self.crear_respuesta()
        self.stock.cantidad = 0
        self.stock.save()
        self.comprobar_aviso(self.client.get(url))

    def test_sin_tema_y_sin_campana_usan_valores_predeterminados(self):
        self.campana.tema_ruleta = None
        self.campana.save(update_fields=['tema_ruleta'])
        respuestas = [
            self.client.get(self.url),
            self.client.get(reverse('ruleta', args=[self.campana.pk, self.tienda.pk, 'SIN-RESPUESTA'])),
            self.client.post(reverse('guardar_premio'), {'codigo_ticket': 'DESCONOCIDO'}),
        ]
        for respuesta in respuestas:
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.context['ruleta_theme_vars'], TemaRuleta.default_css_variables())
            self.assertContains(respuesta, '--ef-text: #eeeeee;')


@override_settings(TIME_ZONE='America/Lima', USE_TZ=True)
class EntregaConcurrenteTests(TransactionTestCase):
    setUp = CampanaCuponTests.setUp
    crear_ticket = CampanaCuponTests.crear_ticket

    @skipUnlessDBFeature('has_select_for_update')
    def test_solicitudes_simultaneas_entregan_un_solo_cupon(self):
        barrera = Barrier(2)

        def entregar():
            try:
                barrera.wait(timeout=10)
                return entregar_premio_directo(self.campana, self.tienda, self.ticket, self.datos).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            futuros = [ejecutor.submit(entregar) for _ in range(2)]
            resultados = [futuro.result(timeout=20) for futuro in futuros]
        self.assertEqual(resultados[0], resultados[1])
        self.assertEqual(Cupon.objects.count(), 1)
        self.assertEqual(EncuestaFijaPremio.objects.count(), 1)
        self.assertEqual(EncuestaFijaRespuesta.objects.count(), 1)
