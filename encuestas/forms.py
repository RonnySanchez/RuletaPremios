from django import forms
from .models import Pregunta, Respuesta, Opcion, TipoIdentificacionCliente
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from datetime import date
from django.urls import reverse
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe



class EncuestaForm(forms.Form):
    """
    Formulario dinámico para generar campos basados en las preguntas de la encuesta.
    """
    codigo_ticket = forms.CharField(max_length=255, required=False, initial='')
    def __init__(self, *args, **kwargs):
        preguntas = kwargs.pop('preguntas')  # preguntas en realidad son instancias de EncuestaPregunta
       # self.fields['codigo_ticket'].required = not self.codigo_ticket
    #    if self.codigo_ticket:
     #       self.fields['codigo_ticket'].initial = self.codigo_ticket
        super(EncuestaForm, self).__init__(*args, **kwargs)
        
        for encuesta_pregunta in preguntas.select_related('pregunta'):
            pregunta = encuesta_pregunta.pregunta  # Aquí accedes a la pregunta real
            if pregunta.tipo_de_pregunta == 'texto':
                self.fields[f'pregunta_{pregunta.id}'] = forms.CharField(label=pregunta.texto, required=True)
            elif pregunta.tipo_de_pregunta == 'numerico':
                self.fields[f'pregunta_{pregunta.id}'] = forms.DecimalField(label=pregunta.texto, required=True)
            elif pregunta.tipo_de_pregunta == 'seleccion_simple':
                opciones = [(pregunta_opcion.opcion.id, pregunta_opcion.opcion.texto_de_opcion)
                            for pregunta_opcion in pregunta.pregunta_opciones.all()]
                self.fields[f'pregunta_{pregunta.id}'] = forms.ChoiceField(
                    label=pregunta.texto,
                    choices=opciones,
                    widget=forms.RadioSelect,
                    required=True 
                    )

class TicketForm(forms.Form):
    """
    Formulario dinámico para pedir ticket.
    """
    codigo_ticket = forms.CharField(max_length=255, required=True, initial='', widget=forms.TextInput(attrs={'class': 'form-control'}))




class EncuestaFijaForm(forms.Form):
    # Campos personales
    nombre = forms.CharField(label="Nombres", max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres'}))
    apellidos = forms.CharField(label="Apellidos", max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos'}))
    telefono = forms.CharField(
        label='Número de teléfono móvil',
        max_length=9,
        min_length=9,
        validators=[RegexValidator(regex=r'^\d{9}$', message="El número de teléfono debe tener exactamente 9 dígitos.")],
        help_text="Introduce un número de teléfono de 9 dígitos", 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono'})
    )
    codigo_ticket = forms.CharField(max_length=255, required=False, initial='', widget=forms.TextInput(attrs={'class': 'form-control'}))

    fnac = forms.DateField(
        label="Fecha de nacimiento",
        required=True,
        # Cambiamos el widget a un campo de texto normal y añadimos un placeholder
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'dd/mm/aaaa'}),
        # Le decimos a Django que el formato de entrada será día/mes/año
        input_formats=["%d/%m/%Y"]
    )

    correo = forms.EmailField(label='Correo electrónico', required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Email'}))
    tipo_identificacion = forms.ChoiceField(
        label='Tipo de identificación',
        choices=TipoIdentificacionCliente.choices,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    DNI = forms.CharField(
        label='DNI/CE/Pasaporte',
        max_length=20,
        min_length=6,
        validators=[RegexValidator(
            regex=r'^[A-Za-z0-9-]{6,20}$',
            message="Usa entre 6 y 20 letras, números o guiones.",
        )],
        help_text="Ingresa tu DNI, CE o pasaporte",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'DNI/CE/Pasaporte'})
    )

    # --- CAMPOS NUEVOS ---
    VALORACION_CHOICES = [
        ('5', '5'), ('4', '4'), ('3', '3'), ('2', '2'), ('1', '1')
    ]

    valoracion_producto = forms.ChoiceField(
        label="¿Cómo valorarías nuestro producto?",
        choices=VALORACION_CHOICES,
        widget=forms.RadioSelect,
        required=True
    )
    valoracion_atencion = forms.ChoiceField(
        label="¿Cómo valorarías nuestra atención?",
        choices=VALORACION_CHOICES,
        widget=forms.RadioSelect,
        required=True
    )
    probabilidad_recomendacion = forms.ChoiceField(
        label="¿Qué tan probable es que recomiendes nuestro producto?",
        choices=VALORACION_CHOICES,
        widget=forms.RadioSelect,
        required=True
    )
    
    comentarios_adicionales = forms.CharField(
        label="¡Cuéntanos más!",
        required=False, # Este campo es opcional
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4})
    )

    acepPolPriv = forms.BooleanField(label=mark_safe("<strong>Acepto</strong> los <a href='#' data-bs-toggle='modal' data-bs-target='#privacyModal'>Términos y Condiciones</a> del módulo de premios de la empresa."))

    #acepPolPriv = forms.BooleanField(label=lazy(lambda: mark_safe(_("Acepto las <a href='#' data-bs-toggle='modal' data-bs-target='#privacyModal'>Políticas de Privacidad</a> de la empresa"))))
    acepProm = forms.BooleanField(label=mark_safe("<strong>Acepto</strong> recibir comunicaciones de promociones, ofertas y publicidad por parte de la marca."), required=False)

    def clean_fnac(self):
        fnac = self.cleaned_data['fnac']
        today = date.today()
        age = today.year - fnac.year - ((today.month, today.day) < (fnac.month, fnac.day))
        
        if age < 18:
            raise ValidationError("Debes ser mayor de 18 años.")
        
        return fnac

    def clean_DNI(self):
        return self.cleaned_data['DNI'].strip().upper()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hacer que el campo 'codigo_ticket' sea de solo lectura
        self.fields['codigo_ticket'].widget.attrs['readonly'] = True
    
