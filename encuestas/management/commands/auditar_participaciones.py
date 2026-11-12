from django.core.management.base import BaseCommand
from django.db.models import Count

from encuestas.models import EncuestaFijaPremio, EncuestaFijaRespuesta


class Command(BaseCommand):
    help = 'Informa duplicados historicos de respuestas y premios. No modifica datos.'

    def handle(self, *args, **options):
        conflictos = False
        for model in (EncuestaFijaRespuesta, EncuestaFijaPremio):
            duplicados = list(
                model.objects.filter(tienda__isnull=False, codigo_ticket__isnull=False)
                .values('encuesta_fija_id', 'tienda_id', 'codigo_ticket')
                .annotate(total=Count('pk')).filter(total__gt=1)
            )
            for grupo in duplicados:
                conflictos = True
                self.stdout.write(f'{model.__name__}: {grupo}')
        for grupo in (
            EncuestaFijaPremio.objects.filter(respuesta__isnull=False)
            .values('respuesta_id').annotate(total=Count('pk')).filter(total__gt=1)
        ):
            conflictos = True
            self.stdout.write(f'Premios para una respuesta: {grupo}')
        if conflictos:
            self.stdout.write(self.style.WARNING('Hay duplicados historicos. El flujo directo usa una tabla nueva con unicidad propia. No se ha modificado ningun registro.'))
        else:
            self.stdout.write(self.style.SUCCESS('Sin duplicados historicos.'))
