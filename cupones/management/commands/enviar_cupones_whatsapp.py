from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cupones.models import NotificacionCuponWhatsApp
from cupones.whatsapp import configuracion_whatsapp, procesar_notificacion_whatsapp


class Command(BaseCommand):
    help = "Procesa nuevos envíos de cupones por WhatsApp autorizados por los clientes."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=25)

    def handle(self, *args, **options):
        if not settings.CUPON_WHATSAPP_HABILITADO:
            self.stdout.write("Envío de WhatsApp deshabilitado.")
            return
        if options["limite"] < 1:
            raise CommandError("--limite debe ser mayor que cero.")
        ids = list(NotificacionCuponWhatsApp.objects.filter(
            estado=NotificacionCuponWhatsApp.Estado.PENDIENTE,
        ).values_list("pk", flat=True)[:options["limite"]])
        if not ids:
            self.stdout.write("Procesados: 0")
            return
        try:
            configuracion = configuracion_whatsapp()
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        resultados = Counter(
            estado for pk in ids
            if (estado := procesar_notificacion_whatsapp(pk, configuracion)) is not None
        )
        for estado, total in sorted(resultados.items()):
            self.stdout.write(f"{estado}: {total}")
        self.stdout.write(f"Procesados: {sum(resultados.values())}")
