from django.utils import timezone
from decimal import Decimal
import random
from django.shortcuts import get_object_or_404, render, redirect
from django.core.serializers import serialize
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.urls import reverse

from cupones import models
from cupones.models import Cupon
from .models import Tienda, TicketConsulta, Encuesta, EncuestaPregunta, Respuesta, Opcion, TiendaPremio, EncuestaFija, EncuestaFijaRespuesta, EncuestaFijaPremio, Premio, TicketVentasEnLinea, transaction
from .forms import EncuestaForm, EncuestaFijaForm, TicketForm
from django.utils.html import format_html
from django.db.models import F
import json



# Create your views here.


@transaction.atomic
def ejecutar_sorteo_ajax(request):
    """
    Se ejecuta vía POST desde el frontend al hacer clic en 'Girar Ruleta'.
    Realiza el cálculo matemático en el servidor de manera segura.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    codigo_ticket = request.POST.get('codigo_ticket')
    tienda_id = request.POST.get('tienda_id')
    encuesta_id = request.POST.get('encuesta_id')

    if not all([codigo_ticket, tienda_id, encuesta_id]):
        return JsonResponse({'error': 'Faltan parámetros'}, status=400)

    try:
        tienda = Tienda.objects.get(id=tienda_id, activa=True)
        encuesta_fija = EncuestaFija.objects.get(id=encuesta_id)
        respuesta = EncuestaFijaRespuesta.objects.get(codigo_ticket=codigo_ticket)
    except (Tienda.DoesNotExist, EncuestaFija.DoesNotExist, EncuestaFijaRespuesta.DoesNotExist):
        return JsonResponse({'error': 'Datos inválidos'}, status=400)

    # 1. Verificar que no haya girado ya (evita doble submit)
    if EncuestaFijaPremio.objects.filter(codigo_ticket=codigo_ticket, encuesta_fija=encuesta_fija).exists():
        return JsonResponse({'error': 'Ya participaste. Premio entregado anteriormente.'}, status=403)

    # 2. Obtener monto del ticket para validar
    ticket_consulta = TicketConsulta.objects.filter(tienda=tienda, codigo=codigo_ticket).first()
    monto = ticket_consulta.monto if ticket_consulta else Decimal('0')

    # 3. Bloquear filas y calcular probabilidades (Evita concurrencia / premio congelado)
    premios_qs = TiendaPremio.objects.select_for_update().filter(tienda=tienda, visible=True)
    
    candidatos = []
    pesos = []

    for tp in premios_qs:
        stock = tp.stock_disponible(monto)
        if stock > 0:
            candidatos.append(tp)
            pesos.append(stock)

    if not candidatos:
        return JsonResponse({'error': 'No hay premios disponibles en este momento.'}, status=400)

    # 4. El Sorteo Matemático
    seleccionado = random.choices(candidatos, weights=pesos, k=1)[0]
    premio = seleccionado.premio
    # 5. Descontar Stock (Tanto para premios reales como para "No premios")
    seleccionado.cantidad -= 1
    seleccionado.save()

    # 6. Registrar en EncuestaFijaPremio (Incluso si es "Suerte en la próxima", para que quede el historial)
    EncuestaFijaPremio.objects.create(
        encuesta_fija=encuesta_fija,
        respuesta=respuesta,
        nombre=respuesta.nombre,
        apellidos=respuesta.apellidos,
        codigo_ticket=codigo_ticket,
        DNI=respuesta.DNI,
        premio=seleccionado.premio,
        tienda=tienda,
    )

    # 7. Devolver el resultado al frontend
    return JsonResponse({
        'status': 'success',
        'premio_id': premio.id,
        'nombre_premio': premio.nombre,
        'descripcion_premio': premio.descripcion or "", # Enviamos la descripción
        'imagen_url': premio.imagen.url if premio.imagen.name else None, # Enviamos la URL de la imagen
        'es_premio_real': premio.es_premio
    })


def consultaEncuestaFijaTiendaApi(request, tienda_id):
    """
    Verifica si una encuesta está asignada a una tienda y devuelve la URL correspondiente.
    """
    # Intentar obtener la tienda
    try:
        tienda = Tienda.objects.get(id_efsystem=tienda_id, activa=True)
    except Tienda.DoesNotExist:
        # Si la tienda no existe, devuelve un status 404 y URL vacía
        return JsonResponse({'resp': '', 'status': 1, 'msg': '', 'texto_imprimir':'', 'token':'nnnnnnnnnn'}, status=200)

    # Validar que la tienda esté asignada a la encuesta
    e_asignada = tienda.encuestasFijas_asignadas_id()
    if not e_asignada:
        # Construye la URL si la encuesta está asignada a la tienda
        return JsonResponse({'resp': '', 'status': 2, 'msg': '', 'texto_imprimir':'', 'token':'nnnnnnnnnn'}, status=200)   

    # Verificar que la petición sea GET
    if request.method == 'GET':#        
        url = reverse('fija', args=[tienda.id, e_asignada])
        return JsonResponse({'resp': url, 'status': 0, 'msg': '', 'texto_imprimir':'tttt tt tttt ttt ttttt tttttt ttttttt ttttttt', 'token':'nnnnnnnnnn'}, status=200)  
    else:
        # Si la petición no es GET, devolver error 405 (Método no permitido)
        return JsonResponse({'resp': '', 'status': 405, 'msg': '', 'texto_imprimir':'', 'token':'nnnnnnnnnn'}, status=405)




def manejo_404(request, exception):
    return render(request, "404.html", {})

def politicas(request):
    return render(request, "politicas.html")


def IndexView(request):
    return render(request, "index.html")

def mensajeCorreo(request):
    if request.method == 'POST':
        return HttpResponse("Datos procesados")
    else:
        return HttpResponse("Este es un form de envío")
    
def sorteo_view(request, tienda_id):
    tienda = get_object_or_404(Tienda, id=tienda_id)
    monto = get_object_or_404(TicketConsulta, tienda=tienda_id)
    try:
        premio = tienda.sortear_premio()
        mensaje = f'¡Felicidades! Has ganado el premio: {premio.nombre}.'
    except ValueError as e:
        mensaje = str(e)
    
    return render(request, 'sorteo_resultado.html', {'mensaje': mensaje})
    
def polls(request, encuesta_id, tienda_id, codigo_ticket=None):
    encuesta = get_object_or_404(Encuesta, id=encuesta_id, activa=True)
    tienda = get_object_or_404(Tienda, id=tienda_id, activa=True)
    preguntas = encuesta.encuesta_preguntas.all()

    if request.method == 'POST':
        form = EncuestaForm(request.POST, preguntas=preguntas)
        if form.is_valid():
            # Extraer el código del ticket del formulario si no se proporciona en la URL
            codigo_ticket = form.cleaned_data.get('codigo_ticket', codigo_ticket)

            # Guardar las respuestas del formulario
            for pregunta_id, respuesta in form.cleaned_data.items():
                if pregunta_id == 'codigo_ticket':
                    continue
                
                # Extraer el ID de la pregunta del campo
                try:
                    pregunta_id = pregunta_id.split('_')[1]  
                    pregunta = get_object_or_404(EncuestaPregunta, pregunta_id=pregunta_id, encuesta=encuesta).pregunta
                except (IndexError, EncuestaPregunta.DoesNotExist):
                    return render(request, 'encuestas/error.html', {'mensaje': 'Pregunta no encontrada'})                

                tipo_pregunta = pregunta.tipo_de_pregunta
                if tipo_pregunta == 'seleccion_simple':
                    opcion = get_object_or_404(Opcion, id=respuesta)
                    Respuesta.objects.create(
                        encuesta=encuesta,
                        pregunta=pregunta,
                        codigo_ticket=codigo_ticket,
                        opcion=opcion,
                        tienda=tienda,
                    )
                else:
                    Respuesta.objects.create(
                        encuesta=encuesta,
                        pregunta=pregunta,
                        codigo_ticket=codigo_ticket,
                        texto_de_respuesta=respuesta,
                        tienda=tienda,
                    )

            return redirect('ruleta', encuesta_id = encuesta_id, tienda_id=tienda.id, codigo_ticket=codigo_ticket)
    else:
        initial_data = {'codigo_ticket': codigo_ticket} if codigo_ticket else {}
        form = EncuestaForm(initial=initial_data, preguntas=preguntas)

    context = {
        'form': form,
        'encuesta': encuesta,
        'tienda': tienda,
        'codigo_ticket': codigo_ticket,
    }
    return render(request, 'poll.html', context)


def ruleta(request, encuesta_id, tienda_id, codigo_ticket):
    # 1. Validaciones iniciales de IDs de sistema
    tienda = get_object_or_404(Tienda, id=tienda_id, activa=True)
    encuesta_fija = get_object_or_404(EncuestaFija, id=encuesta_id)
    
    # 2. ESCUDO ANTI-404: Validar si el ticket existe en las respuestas
    try:
        respuestas = EncuestaFijaRespuesta.objects.get(codigo_ticket=codigo_ticket)
    except EncuestaFijaRespuesta.DoesNotExist:
        # En lugar de crash 404, mostramos error amigable
        return render(request, 'RespEmitida.html', {
            'error': "Ticket inválido o no encontrado.",
            'texto': "Por favor, completa la encuesta primero para participar."
        })

    # 3. Verificar si el usuario ya jugó (Evitar doble premio)
    if EncuestaFijaPremio.objects.filter(codigo_ticket=codigo_ticket, encuesta_fija=encuesta_fija).exists():
        return render(request, 'RespEmitida.html', {
            'error': "Ya se ha entregado un premio con este código de ticket.",
            'texto': "Gracias por tu participación"
        })

    # 4. Cálculo de Monto y Premios Disponibles
    ticket_consulta = TicketConsulta.objects.filter(
        tienda=tienda,
        codigo=codigo_ticket
    ).first()

    monto = ticket_consulta.monto if ticket_consulta else Decimal('0')
     
    # 5. Armamos la lista de premios visibles
    premios_qs = TiendaPremio.objects.filter(tienda=tienda, visible=True)

    premio_data = []
    for tp in premios_qs:
        stock = tp.stock_disponible(monto)
        # Solo enviamos a la ruleta lo que tenga stock o sea opción de "No premio"
        if stock > 0 or not tp.premio.es_premio:
            premio_data.append({
                'id': tp.premio.id,
                'nombre': tp.premio.nombre,
                'stock': stock,
                'probabilidad': stock,
                'es_premio': tp.premio.es_premio 
            })

    # Convertimos a JSON para el motor de la ruleta en Javascript
    premios_json = json.dumps(premio_data)
    
    context = {
        'tienda': tienda,
        'encuesta_id': encuesta_fija.id,
        'codigo_ticket': codigo_ticket,
        'premiosDat': premios_json,
        'respuestas': respuestas,
        'tipojuego': encuesta_fija.tipo_juego,
    }
    
    # 6. Redirección al Template correspondiente
    if encuesta_fija.tipo_juego == EncuestaFija.TipoJuego.CAJAS:
        return render(request, 'tabla_regalos.html', context)
    else:
        return render(request, 'ruleta.html', context)


def pideticket(request, encuesta_id, tienda_id):
    encuesta_fija = get_object_or_404(EncuestaFija, id=encuesta_id, activa=True)
    tienda = get_object_or_404(Tienda, id=tienda_id, activa=True)
    form = TicketForm()

    # Validar que la tienda esté asignada a la encuesta
    tiendas_asignadas = encuesta_fija.get_tiendas_asignadas()
    if not tiendas_asignadas.filter(id=tienda.id).exists():
        return render(request, 'RespEmitida.html', {
            'error': "! No hay sorteos en esta tienda !.",
            'texto': "Gracias por tu participación"
        })

    if request.method == 'POST':
        # Capturar el código del ticket desde el formulario
        codigo_ticket = request.POST.get('codigo_ticket')
        if codigo_ticket:
            # Aquí puedes agregar validación del ticket si es necesario
            # Validar si el ticket cumple con las condiciones
            return redirect('fijaConTicket', encuesta_id=encuesta_id, tienda_id=tienda.id, codigo_ticket=codigo_ticket)
        else:
            # Si no se ingresó un código, vuelve a renderizar la misma página con un mensaje de error
            return render(request, 'formulario_ticket.html', {
                'tienda': tienda,
                'encuesta': encuesta_fija,
                'form': form,
                'error': '¡Por favor ingresa un código de ticket válido!',
            })
    else:
        # Renderizar la página por primera vez (método GET)
        return render(request, 'ticket.html', {
            'tienda': tienda,
            'encuesta': encuesta_fija,
            'form': form,
        })
    



def encuestafijaticket(request, tienda_id, encuesta_id, codigo_ticket):
    encuesta_fija = get_object_or_404(EncuestaFija, id=encuesta_id, activa=True)
    tienda = get_object_or_404(Tienda, id=tienda_id, activa=True)

    # 1. Validar tienda asignada
    t_asignadas = encuesta_fija.get_tiendas_asignadas()
    if not t_asignadas.filter(id=tienda.id).exists():
        return render(request, 'RespEmitida.html', {
                'error': "! No hay sorteos en esta tienda !.",
                'texto': "Gracias por tu participación"
            })

    # 2. Verificar stock general
    if tienda.premios_stock() <= 0:
        return render(request, 'RespEmitida.html', {
            'error': "! Se agotaron los premios !.",
            'texto': "Gracias por tu participación"
    })

    # 3. Validación de Ticket Online (Ventas en Línea)
    if tienda.requiere_validacion_ticket:
        try:
            ticket = TicketVentasEnLinea.objects.get(nro_ticket=codigo_ticket)

            if ticket.utilizado:
                try:
                    premio_existente = EncuestaFijaPremio.objects.get(codigo_ticket=codigo_ticket, encuesta_fija=encuesta_fija)
                    
                    # --- Lógica de mensaje dinámico ---
                    tiendaprem = premio_existente.tienda
                    nombreprem = premio_existente.nombre
                    apellidosprem = premio_existente.apellidos
                    prem = premio_existente.premio
                    idnombre = premio_existente.respuesta.DNI

                    if premio_existente.premio.es_premio:
                        # Caso: Ganó un premio físico
                        errorprem = f"Este premio ya ha sido entregado en<br><h3>{tiendaprem}</h3>Cliente <br><h3>{nombreprem} {apellidosprem}</h3><h3>({idnombre})</h3>Premio <h3>{prem}</h3><br>"
                    else:
                        # Caso: Salió "Sigue intentando" o similar
                        errorprem = f"Este ticket ya participó en la Ruleta en<br><h3>{tiendaprem}</h3>Cliente <br><h3>{nombreprem} {apellidosprem}</h3><h3>({idnombre})</h3>Resultado: <h3>{prem}</h3><br>Este ticket no obtuvo premio físico.<br>"
                    
                    return render(request, 'RespEmitida.html', { 'error': errorprem, 'texto': "¡Gracias por participar!" })
                
                except EncuestaFijaPremio.DoesNotExist:
                    return redirect('ruleta', encuesta_id=encuesta_id, tienda_id=tienda.id, codigo_ticket=codigo_ticket)
            
            else:
                if ticket.esta_vencido():
                    return render(request, 'RespEmitida.html', {
                        'error': "Lo sentimos, este código de ticket ha expirado.",
                        'texto': "¡Gracias por participar!"
                    })
        except TicketVentasEnLinea.DoesNotExist:
            return render(request, 'RespEmitida.html', {
                'error': "El código de ticket ingresado no es válido.",
                'texto': "Gracias por tu participación"
            })

    # 4. Validación para tickets generales / Sin validación online obligatoria
    plantilla = 'poll_f1.html'
    if codigo_ticket:
        try:
            respuesta_existente = EncuestaFijaRespuesta.objects.get(codigo_ticket=codigo_ticket, encuesta_fija=encuesta_fija)
            try:
                premio_existente = EncuestaFijaPremio.objects.get(codigo_ticket=codigo_ticket, encuesta_fija=encuesta_fija)
                
                tiendaprem = premio_existente.tienda
                nombreprem = premio_existente.nombre
                apellidosprem = premio_existente.apellidos
                prem = premio_existente.premio
                idnombre = premio_existente.respuesta.DNI

                if premio_existente.premio.es_premio:
                    # Mensaje para Ganadores
                    errorprem = f"Este premio ya ha sido entregado en<br><h3>{tiendaprem}</h3>Cliente Ganador<br><h3>{nombreprem} {apellidosprem}</h3><h3>({idnombre})</h3>Premio <h3>{prem}</h3><br>"
                else:
                    # Mensaje para No Ganadores
                    errorprem = f"Este ticket ya participó en la Ruleta en<br><h3>{tiendaprem}</h3>Cliente <br><h3>{nombreprem} {apellidosprem}</h3><h3>({idnombre})</h3>Resultado: <h3>{prem}</h3><br>No se obtuvo un premio físico en esta ocasión.<br>"

                return render(request, 'RespEmitida.html', {
                    'error': errorprem,
                    'texto': "¡Gracias por participar en nuestra Ruleta de Premios!"
                })
            except EncuestaFijaPremio.DoesNotExist:
                return redirect('ruleta', encuesta_id=encuesta_id, tienda_id=tienda.id, codigo_ticket=codigo_ticket)
        except EncuestaFijaRespuesta.DoesNotExist:
            pass
    else:
        plantilla = 'ticket.html'

    # 5. Manejo del POST (Guardar Encuesta)
    if request.method == 'POST':
        form = EncuestaFijaForm(request.POST)
        if form.is_valid():
            codigo_ticket_form = form.cleaned_data['codigo_ticket']
            
            if EncuestaFijaRespuesta.objects.filter(codigo_ticket=codigo_ticket_form, encuesta_fija=encuesta_fija).exists():
                return render(request, 'RespEmitida.html', {
                    'error': "Ya se ha enviado una respuesta..",
                    'texto': "Gracias por tu participación"
                })            
            
            respuesta = EncuestaFijaRespuesta(
                encuesta_fija=encuesta_fija,
                nombre=form.cleaned_data['nombre'],
                apellidos=form.cleaned_data['apellidos'],
                telefono=form.cleaned_data['telefono'],
                codigo_ticket=form.cleaned_data['codigo_ticket'],
                fnac=form.cleaned_data['fnac'],
                correo=form.cleaned_data['correo'],
                DNI=form.cleaned_data['DNI'],
                tienda = Tienda.objects.get(id=tienda_id),
                acepPolPriv=form.cleaned_data['acepPolPriv'],
                acepProm=form.cleaned_data.get('acepProm', False),
                valoracion_producto=form.cleaned_data['valoracion_producto'],
                valoracion_atencion=form.cleaned_data['valoracion_atencion'],
                probabilidad_recomendacion=form.cleaned_data['probabilidad_recomendacion'],
                comentarios_adicionales=form.cleaned_data.get('comentarios_adicionales')
            )
            respuesta.save()

            if tienda.requiere_validacion_ticket:
                try:
                    ticket_a_marcar = TicketVentasEnLinea.objects.get(nro_ticket=codigo_ticket_form)
                    ticket_a_marcar.utilizado = True
                    ticket_a_marcar.save()
                except TicketVentasEnLinea.DoesNotExist:
                    pass

            return redirect('ruleta', encuesta_id=encuesta_id, tienda_id=tienda.id, codigo_ticket=codigo_ticket)
    else:
        initial_data = {'codigo_ticket': codigo_ticket} if codigo_ticket else {}
        form = EncuestaFijaForm(initial=initial_data)

    context = {
        'encuesta': encuesta_fija,
        'tienda': tienda,
        'form': form,
        'calificacion': 0,
        'codigo_ticket': codigo_ticket,
    }

    return render(request, plantilla, context)




def guardar_premio(request):
    # Solo permitimos POST para mayor seguridad
    if request.method != 'POST':
        return redirect('index')

    # Capturamos los datos que envía nuestro nuevo Javascript
    codigo_ticket = request.POST.get('codigo_ticket')
    # premio_id = request.POST.get('premio_id') # Opcional, con el ticket basta

    # 1. BUSCAMOS EL PREMIO QUE YA FUE CREADO
    # Buscamos el registro que la función AJAX generó hace un segundo
    try:
        entregado = EncuestaFijaPremio.objects.get(codigo_ticket=codigo_ticket)
    except EncuestaFijaPremio.DoesNotExist:
        # Si alguien intenta entrar a esta URL sin haber girado la ruleta
        return render(request, 'RespEmitida.html', {
            'error': "No se encontró un registro de premio para este ticket.",
            'texto': "Por favor, asegúrate de completar el sorteo correctamente."
        })

    # 2. LOG DE VERIFICACIÓN (Opcional, para tus pruebas en consola)
    print(f"--- Mostrando Pantalla Final ---")
    print(f"Ticket: {entregado.codigo_ticket}")
    print(f"Premio: {entregado.premio.nombre}")
    print(f"Cliente: {entregado.nombre} {entregado.apellidos}")

    # 3. ENVIAMOS EL CONTEXTO A LA PLANTILLA
    # 'entregado' es la instancia de EncuestaFijaPremio
    context = {
        'premio': entregado,
    }
    
    if entregado.premio.es_premio: 
        return render(request, 'premio_entregado1.html', context)
    else:
        return render(request, 'sin_premio.html', context)




def vista_juego_regalos(request, encuesta_id, tienda_id, codigo_ticket):
    """
    Esta vista maneja la lógica para el juego de la tabla de regalos.
    """

    tienda = get_object_or_404(Tienda, id=tienda_id, activa=True)
    encuesta_fija = get_object_or_404(EncuestaFija, id=encuesta_id)
    respuestas = get_object_or_404(EncuestaFijaRespuesta, codigo_ticket=codigo_ticket)


    if codigo_ticket:
        try:
            # Verificar si ya existe un premio entregado con ese código de ticket
            premio_existente = EncuestaFijaPremio.objects.get(
                codigo_ticket=codigo_ticket, encuesta_fija=encuesta_fija
            )
            # Si ya existe, mostrar un mensaje o redirigir
            return render(request, 'RespEmitida.html', {
                'error': "Ya se ha entregado un premio con este código de ticket.",
                'texto': "Gracias por tu participación"
            })
        except EncuestaFijaPremio.DoesNotExist:
            # No existe un premio con este código, continuar con la lógica normal de la ruleta
            pass




    # --- 1. Lógica para seleccionar el premio ---
    # Aquí debes replicar o adaptar la lógica que usas para la ruleta
    # para determinar qué premio (cupón) se otorgará.
    # Por ejemplo, podrías buscar cupones activos con usos disponibles.
    
    # A MODO DE EJEMPLO: seleccionamos el primer cupón activo que encontramos.
    # ¡DEBES REEMPLAZAR ESTO CON TU LÓGICA REAL DE PROBABILIDAD Y DISPONIBILIDAD!
    premio_seleccionado = Cupon.objects.filter(
        estatus='ACTIVO',
        usos_actuales__lt=F('limite_usos') # Se quita el prefijo 'models.'
    ).first()
    
    premio_obtenido_str = "¡Sigue intentando!" # Mensaje por defecto si no hay premios
    if premio_seleccionado:
        # Formateamos el string del premio según su tipo
        if premio_seleccionado.tipo == 'PORCENTAJE':
            premio_obtenido_str = f"un Cupón del {int(premio_seleccionado.valor)}% de descuento"
        else:
            premio_obtenido_str = f"un Cupón de S/{premio_seleccionado.valor:.2f} de descuento"

    # --- 2. Lógica para determinar el intento ganador ---
    # Se decide aleatoriamente si el usuario ganará en el 1er, 2do o 3er intento.
    intento_ganador = random.choice([1, 2, 3])

    # --- 3. Construir el contexto para la plantilla ---
    # Este diccionario contiene las variables que tu HTML necesita.
    context = {
        'intento_ganador': intento_ganador,
        'premio_obtenido': premio_obtenido_str,
        'rango_celdas': range(9),
    }

    # 4. Renderizar la plantilla HTML y pasarle el contexto
    # Asegúrate de que tu archivo esté en 'templates/encuestas/tabla_regalos.html'
    return render(request, 'tabla_regalos.html', context)



def simulador_pantallas(request):
    # Solo administradores o personal autorizado debería ver esto (opcional pero recomendado)
    if not request.user.is_staff:
        return redirect('index')

    if request.method == 'POST':
        premio_id = request.POST.get('premio_id')
        
        # Traemos el premio real de la base de datos
        premio_real = Premio.objects.get(id=premio_id)
        
        # Creamos un objeto falso EN MEMORIA (no afecta tu base de datos ni descuenta stock)
        class MockEntregado:
            pass
            
        entregado_falso = MockEntregado()
        entregado_falso.nombre = "Juan"
        entregado_falso.apellidos = "Pérez (Prueba)"
        entregado_falso.DNI = "12345678"
        entregado_falso.codigo_ticket = "SIMULADOR-999"
        entregado_falso.premio = premio_real
        
        context = {'premio': entregado_falso}
        
        # Usamos tu misma lógica de desvío
        if premio_real.es_premio:
            return render(request, 'premio_entregado1.html', context)
        else:
            return render(request, 'sin_premio.html', context)

    # Si entran por GET, mostramos el selector de premios
    premios = Premio.objects.all()
    return render(request, 'simulador_form.html', {'premios': premios})



