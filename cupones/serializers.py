from decimal import Decimal

from rest_framework import serializers

from encuestas.models import Tienda
from .models import Cupon, PresentacionCupon, TipoIdentificacion, UsoCupon


class PresentacionCuponSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentacionCupon
        fields = ["nombre", "codigo_efsystem"]


class CuponSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)
    categorias = serializers.StringRelatedField(many=True, read_only=True)
    presentaciones = PresentacionCuponSerializer(many=True, read_only=True)
    requiere_identificacion = serializers.SerializerMethodField()

    def get_requiere_identificacion(self, obj):
        return not obj.transferible

    class Meta:
        model = Cupon
        fields = [
            "codigo",
            "tipo",
            "valor",
            "categorias",
            "presentaciones",
            "cantidad_maxima_productos",
            "minimo_compra",
            "maximo_descuento",
            "inicio",
            "vencimiento",
            "transferible",
            "requiere_identificacion",
            "is_active",
            "limite_usos",
            "usos_actuales",
        ]


class DatosValidacionCuponSerializer(serializers.Serializer):
    codigo = serializers.CharField(required=True)
    tienda = serializers.SlugRelatedField(
        slug_field="id_efsystem",
        queryset=Tienda.objects.all(),
        required=True,
    )
    monto_total = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
    )
    categoria = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    presentacion_codigo = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cantidad_productos = serializers.IntegerField(required=False, min_value=1)
    monto_aplicable = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0.01'), required=False,
    )
    tipo_identificacion = serializers.ChoiceField(
        choices=TipoIdentificacion.choices,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    numero_identificacion = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
    )


class ConsumirCuponSerializer(DatosValidacionCuponSerializer):
    idempotency_key = serializers.CharField(max_length=100, required=True)
    nro_referencia = serializers.CharField(max_length=255, required=False, allow_blank=True)
    monto_descuento = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False,
    )


class UsoCuponSerializer(serializers.ModelSerializer):
    codigo = serializers.CharField(write_only=True, required=True)
    tienda = serializers.SlugRelatedField(
        slug_field="id_efsystem",
        queryset=Tienda.objects.all(),
        required=True,
    )

    class Meta:
        model = UsoCupon
        fields = ["codigo", "tienda", "nro_referencia", "monto_total", "monto_descuento"]


class UsoCuponRespuestaSerializer(serializers.ModelSerializer):
    codigo = serializers.CharField(source="cupon.codigo", read_only=True)
    tienda = serializers.CharField(source="tienda.id_efsystem", read_only=True)

    class Meta:
        model = UsoCupon
        fields = [
            "codigo",
            "tienda",
            "idempotency_key",
            "nro_referencia",
            "monto_total",
            "monto_descuento",
            "cantidad_productos",
            "monto_aplicable",
            "presentacion_codigo",
            "fecha_uso",
        ]
