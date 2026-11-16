"""Перестановка каналов и числовые характеристики RGB-изображения."""
import io
import base64
import numpy as np
from PIL import Image, ImageOps
import matplotlib
matplotlib.use('Agg')  # Рендеринг графиков без оконного интерфейса.
from matplotlib.figure import Figure

ORDERS = ('RGB', 'RBG', 'GRB', 'GBR', 'BRG', 'BGR')

def decode_image(stream):
    """Проверить файл, ориентацию EXIF и ограничение размера до декодирования."""
    image = Image.open(stream)
    if image.format not in ('PNG', 'JPEG', 'WEBP'):
        raise ValueError('Допустимы только PNG, JPEG и WebP.')
    if image.width * image.height > 4_000_000:
        raise ValueError('Изображение превышает 4 миллиона пикселей.')
    image.load()
    return ImageOps.exif_transpose(image).convert('RGB')

def permute_channels(image, order):
    """Например, BGR: новый R равен старому B, новый G старому G."""
    if order not in ORDERS:
        raise ValueError('Недопустимый порядок каналов.')
    channels = dict(zip('RGB', image.split()))
    return Image.merge('RGB', tuple(channels[channel] for channel in order))

def metrics(image):
    """Гистограмма и профили: x усредняется по строкам, y по столбцам."""
    a = np.asarray(image, dtype=np.uint8)
    return {
        'width': image.width,
        'height': image.height,
        'histogram': [np.bincount(a[:, :, k].ravel(), minlength=256).tolist()
                      for k in range(3)],
        'mean_by_x': a.mean(axis=0).tolist(),
        'mean_by_y': a.mean(axis=1).tolist(),
        'mean_rgb': a.mean(axis=(0, 1)).tolist(),
    }

def png_data(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

def figure_data(figure):
    buffer = io.BytesIO()
    figure.savefig(buffer, format='png', dpi=120, bbox_inches='tight')
    figure.clear()
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

def charts(data, prefix):
    """Отдельные фигуры не используют глобальный pyplot и общие файлы."""
    result = {}
    figure = Figure(figsize=(7, 3.5))
    ax = figure.subplots()
    for k, color in enumerate(('red', 'green', 'blue')):
        ax.plot(range(256), data['histogram'][k], color=color, label='RGB'[k])
    ax.set(xlabel='Интенсивность 0–255', ylabel='Количество пикселей',
           title=prefix + ': распределение каналов')
    ax.grid(alpha=.25)
    ax.legend()
    result['histogram'] = figure_data(figure)
    for key, axis_name in [('mean_by_x', 'X: координата столбца'),
                           ('mean_by_y', 'Y: координата строки')]:
        figure = Figure(figsize=(7, 3.5))
        ax = figure.subplots()
        values = np.asarray(data[key])
        for k, color in enumerate(('red', 'green', 'blue')):
            ax.plot(values[:, k], color=color, label='RGB'[k])
        ax.set(xlabel=axis_name, ylabel='Средняя интенсивность', ylim=(0, 255),
               title=prefix + ': среднее значение цвета')
        ax.grid(alpha=.25)
        ax.legend()
        result[key] = figure_data(figure)
    return result


def encoded_data(image, output_format):
    """Кодировать результат в выбранный формат, включая реальный MIME."""
    formats = {'PNG': ('image/png', 'png'),
               'JPEG': ('image/jpeg', 'jpg'),
               'WEBP': ('image/webp', 'webp')}
    if output_format not in formats:
        raise ValueError('Недопустимый выходной формат.')
    mime, extension = formats[output_format]
    options = {}
    if output_format == 'JPEG':
        options = {'quality': 95, 'subsampling': 0}
    elif output_format == 'WEBP':
        options = {'lossless': True}
    buffer = io.BytesIO()
    image.convert('RGB').save(buffer, format=output_format, **options)
    data = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:{mime};base64,{data}', extension
