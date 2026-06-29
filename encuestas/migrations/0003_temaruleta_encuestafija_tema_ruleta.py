from django.core.validators import RegexValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('encuestas', '0002_premio_es_premio_tiendapremio_fecha_activacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='TemaRuleta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('fondo_ruleta', models.CharField(default='#003468', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Fondo de ruleta')),
                ('fondo_premio', models.CharField(default='#003468', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Fondo con premio')),
                ('fondo_sin_premio', models.CharField(default='#003468', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Fondo sin premio')),
                ('texto_principal', models.CharField(default='#eeeeee', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Texto principal')),
                ('texto_secundario', models.CharField(default='#c9c9c9', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Texto secundario')),
                ('segmento_1', models.CharField(default='#c54954', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Segmento 1')),
                ('segmento_2', models.CharField(default='#003468', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Segmento 2')),
                ('segmento_3', models.CharField(default='#97222d', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Segmento 3')),
                ('segmento_4', models.CharField(default='#6b96b8', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Segmento 4')),
                ('segmento_5', models.CharField(default='#e1253c', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Segmento 5')),
                ('segmento_6', models.CharField(default='#97a1a7', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Segmento 6')),
                ('puntero_inicio', models.CharField(default='#e1253c', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Puntero inicio')),
                ('puntero_medio', models.CharField(default='#c54954', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Puntero medio')),
                ('puntero_fin', models.CharField(default='#97222d', help_text='Formato #RRGGBB', max_length=7, validators=[RegexValidator(message='Ingrese un color hexadecimal valido, por ejemplo #003468.', regex='^#[0-9A-Fa-f]{6}$')], verbose_name='Puntero fin')),
                ('activo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Tema de Ruleta',
                'verbose_name_plural': 'Temas de Ruleta',
                'ordering': ['nombre'],
            },
        ),
        migrations.AddField(
            model_name='encuestafija',
            name='tema_ruleta',
            field=models.ForeignKey(blank=True, help_text='Define los colores usados por la ruleta y sus pantallas de resultado.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='encuestas_fijas', to='encuestas.temaruleta', verbose_name='Tema visual de ruleta'),
        ),
    ]
