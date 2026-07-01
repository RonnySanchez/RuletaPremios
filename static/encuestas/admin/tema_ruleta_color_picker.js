(function () {
    var DEFAULT_COLOR = '#003468';
    var DEFAULT_PALETTE = [
        '#003468',
        '#c54954',
        '#97222d',
        '#6b96b8',
        '#0d47a1',
        '#0a367a',
        '#1e88e5',
        '#1565c0',
        '#6c757d',
        '#198754',
        '#ffc107',
        '#dc3545',
        '#eeeeee',
        '#c9c9c9',
        '#111827',
        '#f4f6f9',
        '#ffffff',
        '#333333'
    ];

    function getPresetColors(input) {
        var presetColors = DEFAULT_PALETTE;

        if (input.dataset.presetColors) {
            try {
                presetColors = JSON.parse(input.dataset.presetColors);
            } catch (error) {
                presetColors = DEFAULT_PALETTE;
            }
        }

        if (!Array.isArray(presetColors)) {
            presetColors = DEFAULT_PALETTE;
        }

        var colors = presetColors
            .filter(isHexColor)
            .map(function (color) {
                return color.toLowerCase();
            });

        return Array.from(new Set(colors.length ? colors : DEFAULT_PALETTE));
    }

    function isHexColor(value) {
        return /^#[0-9A-Fa-f]{6}$/.test(value || '');
    }

    function normalizeHex(value) {
        return isHexColor(value) ? value.toLowerCase() : DEFAULT_COLOR;
    }

    function hexToRgb(value) {
        var hex = normalizeHex(value).slice(1);
        return {
            r: parseInt(hex.slice(0, 2), 16),
            g: parseInt(hex.slice(2, 4), 16),
            b: parseInt(hex.slice(4, 6), 16)
        };
    }

    function toHexPart(value) {
        return Math.max(0, Math.min(255, parseInt(value, 10) || 0))
            .toString(16)
            .padStart(2, '0');
    }

    function rgbToHex(red, green, blue) {
        return '#' + toHexPart(red) + toHexPart(green) + toHexPart(blue);
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function rgbToHsv(red, green, blue) {
        var r = red / 255;
        var g = green / 255;
        var b = blue / 255;
        var max = Math.max(r, g, b);
        var min = Math.min(r, g, b);
        var delta = max - min;
        var hue = 0;

        if (delta !== 0) {
            if (max === r) {
                hue = 60 * (((g - b) / delta) % 6);
            } else if (max === g) {
                hue = 60 * (((b - r) / delta) + 2);
            } else {
                hue = 60 * (((r - g) / delta) + 4);
            }
        }

        if (hue < 0) {
            hue += 360;
        }

        return {
            h: Math.round(hue),
            s: max === 0 ? 0 : delta / max,
            v: max
        };
    }

    function hsvToRgb(hue, saturation, value) {
        var h = ((Number(hue) || 0) % 360 + 360) % 360;
        var s = clamp(Number(saturation) || 0, 0, 1);
        var v = clamp(Number(value) || 0, 0, 1);
        var chroma = v * s;
        var x = chroma * (1 - Math.abs((h / 60) % 2 - 1));
        var m = v - chroma;
        var r = 0;
        var g = 0;
        var b = 0;

        if (h < 60) {
            r = chroma;
            g = x;
        } else if (h < 120) {
            r = x;
            g = chroma;
        } else if (h < 180) {
            g = chroma;
            b = x;
        } else if (h < 240) {
            g = x;
            b = chroma;
        } else if (h < 300) {
            r = x;
            b = chroma;
        } else {
            r = chroma;
            b = x;
        }

        return {
            r: Math.round((r + m) * 255),
            g: Math.round((g + m) * 255),
            b: Math.round((b + m) * 255)
        };
    }

    function hsvToHex(hue, saturation, value) {
        var rgb = hsvToRgb(hue, saturation, value);
        return rgbToHex(rgb.r, rgb.g, rgb.b);
    }

    function attachColorPicker(input) {
        if (input.dataset.colorPickerAttached === '1') {
            return;
        }

        input.dataset.colorPickerAttached = '1';

        var wrapper = document.createElement('span');
        wrapper.className = 'ruleta-color-control';

        var parent = input.parentNode;
        parent.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        var preview = document.createElement('button');
        preview.type = 'button';
        preview.className = 'ruleta-color-preview';
        preview.title = 'Seleccionar color';
        preview.setAttribute('aria-label', 'Seleccionar color');

        var panel = createFallbackPanel(input, preview, getPresetColors(input));

        function syncFromText() {
            if (isHexColor(input.value)) {
                preview.style.backgroundColor = input.value;
                updateFallbackPanel(panel, input.value);
            }
        }

        preview.addEventListener('click', function (event) {
            event.preventDefault();
            toggleFallbackPanel(panel);
        });

        input.addEventListener('input', syncFromText);
        input.addEventListener('change', syncFromText);

        wrapper.appendChild(preview);
        document.body.appendChild(panel);
        syncFromText();
    }

    function createFallbackPanel(sourceInput, preview, presetColors) {
        var panel = document.createElement('span');
        panel.className = 'ruleta-color-panel';
        panel.hidden = true;

        var gradient = document.createElement('span');
        gradient.className = 'ruleta-color-gradient';
        gradient.setAttribute('role', 'button');
        gradient.setAttribute('tabindex', '0');
        gradient.setAttribute('aria-label', 'Seleccionar saturacion y brillo');

        var gradientPointer = document.createElement('span');
        gradientPointer.className = 'ruleta-color-gradient-pointer';
        gradient.appendChild(gradientPointer);
        panel.appendChild(gradient);

        var hueRow = document.createElement('label');
        hueRow.className = 'ruleta-color-hue-row';

        var hueLabel = document.createElement('span');
        hueLabel.textContent = 'Tono';

        var hueSlider = document.createElement('input');
        hueSlider.type = 'range';
        hueSlider.className = 'ruleta-color-hue';
        hueSlider.min = '0';
        hueSlider.max = '360';
        hueSlider.step = '1';

        hueRow.appendChild(hueLabel);
        hueRow.appendChild(hueSlider);
        panel.appendChild(hueRow);

        var hexField = document.createElement('input');
        hexField.type = 'text';
        hexField.className = 'ruleta-color-panel-hex';
        hexField.maxLength = 7;
        hexField.pattern = '^#[0-9A-Fa-f]{6}$';
        panel.appendChild(hexField);

        var swatches = document.createElement('span');
        swatches.className = 'ruleta-color-swatches';
        var swatchButtons = [];

        presetColors.forEach(function (color) {
            var swatch = document.createElement('button');
            swatch.type = 'button';
            swatch.className = 'ruleta-color-swatch';
            swatch.dataset.color = color;
            swatch.style.backgroundColor = color;
            swatch.title = color;
            swatch.setAttribute('aria-label', color);
            swatch.addEventListener('click', function () {
                setSourceColor(color);
            });
            swatchButtons.push(swatch);
            swatches.appendChild(swatch);
        });

        panel.appendChild(swatches);

        var channels = [
            ['r', 'Rojo'],
            ['g', 'Verde'],
            ['b', 'Azul']
        ];
        var sliders = {};

        channels.forEach(function (channel) {
            var row = document.createElement('label');
            row.className = 'ruleta-color-slider';

            var label = document.createElement('span');
            label.textContent = channel[1];

            var slider = document.createElement('input');
            slider.type = 'range';
            slider.min = '0';
            slider.max = '255';
            slider.step = '1';
            slider.dataset.channel = channel[0];

            sliders[channel[0]] = slider;
            row.appendChild(label);
            row.appendChild(slider);
            panel.appendChild(row);
        });

        function setSourceColor(value) {
            if (!isHexColor(value)) {
                return;
            }

            sourceInput.value = value.toLowerCase();
            preview.style.backgroundColor = sourceInput.value;
            updateFallbackPanel(panel, sourceInput.value);
            sourceInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function setFromGradient(clientX, clientY) {
            var rect = gradient.getBoundingClientRect();
            var saturation = clamp((clientX - rect.left) / rect.width, 0, 1);
            var value = 1 - clamp((clientY - rect.top) / rect.height, 0, 1);
            setSourceColor(hsvToHex(hueSlider.value, saturation, value));
        }

        function startGradientDrag(event) {
            event.preventDefault();
            setFromGradient(event.clientX, event.clientY);

            function handleMove(moveEvent) {
                setFromGradient(moveEvent.clientX, moveEvent.clientY);
            }

            function stopDrag() {
                document.removeEventListener('pointermove', handleMove);
                document.removeEventListener('pointerup', stopDrag);
            }

            document.addEventListener('pointermove', handleMove);
            document.addEventListener('pointerup', stopDrag);
        }

        gradient.addEventListener('pointerdown', startGradientDrag);
        gradient.addEventListener('keydown', function (event) {
            var hsv = panel._ruletaColorControls.hsv;
            var step = event.shiftKey ? 0.1 : 0.02;
            var handled = true;

            if (event.key === 'ArrowLeft') {
                hsv.s = clamp(hsv.s - step, 0, 1);
            } else if (event.key === 'ArrowRight') {
                hsv.s = clamp(hsv.s + step, 0, 1);
            } else if (event.key === 'ArrowUp') {
                hsv.v = clamp(hsv.v + step, 0, 1);
            } else if (event.key === 'ArrowDown') {
                hsv.v = clamp(hsv.v - step, 0, 1);
            } else {
                handled = false;
            }

            if (handled) {
                event.preventDefault();
                setSourceColor(hsvToHex(hsv.h, hsv.s, hsv.v));
            }
        });

        hueSlider.addEventListener('input', function () {
            var hsv = panel._ruletaColorControls.hsv;
            setSourceColor(hsvToHex(hueSlider.value, hsv.s, hsv.v));
        });

        function setFromSliders() {
            setSourceColor(rgbToHex(sliders.r.value, sliders.g.value, sliders.b.value));
        }

        Object.keys(sliders).forEach(function (key) {
            sliders[key].addEventListener('input', setFromSliders);
        });

        hexField.addEventListener('input', function () {
            if (isHexColor(hexField.value)) {
                setSourceColor(hexField.value);
            }
        });

        var defaultRgb = hexToRgb(DEFAULT_COLOR);

        panel._ruletaColorControls = {
            gradient: gradient,
            gradientPointer: gradientPointer,
            hexField: hexField,
            hueSlider: hueSlider,
            hsv: rgbToHsv(defaultRgb.r, defaultRgb.g, defaultRgb.b),
            preview: preview,
            sliders: sliders,
            swatches: swatchButtons
        };

        return panel;
    }

    function updateFallbackPanel(panel, value) {
        if (!panel || !panel._ruletaColorControls || !isHexColor(value)) {
            return;
        }

        var rgb = hexToRgb(value);
        var hsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
        var controls = panel._ruletaColorControls;
        controls.hsv = hsv;
        controls.gradient.style.setProperty('--ruleta-color-hue', hsvToHex(hsv.h, 1, 1));
        controls.gradientPointer.style.left = (hsv.s * 100) + '%';
        controls.gradientPointer.style.top = ((1 - hsv.v) * 100) + '%';
        controls.hexField.value = value.toLowerCase();
        controls.hueSlider.value = hsv.h;
        controls.sliders.r.value = rgb.r;
        controls.sliders.g.value = rgb.g;
        controls.sliders.b.value = rgb.b;
        controls.swatches.forEach(function (swatch) {
            var isSelected = swatch.dataset.color.toLowerCase() === value.toLowerCase();
            swatch.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });
    }

    function toggleFallbackPanel(panel) {
        var shouldOpen = panel.hidden;
        closeFallbackPanels();
        panel.hidden = !shouldOpen;

        if (shouldOpen) {
            positionFallbackPanel(panel);
            panel._ruletaColorControls.hexField.focus();
            panel._ruletaColorControls.hexField.select();
        }
    }

    function positionFallbackPanel(panel) {
        var preview = panel._ruletaColorControls.preview;
        var rect = preview.getBoundingClientRect();
        var panelWidth = 280;
        var left = rect.left;
        var top = rect.bottom + 6;
        var maxLeft = Math.max(8, window.innerWidth - panelWidth - 8);

        panel.style.left = Math.min(left, maxLeft) + 'px';
        panel.style.top = top + 'px';
    }

    function closeFallbackPanels() {
        document.querySelectorAll('.ruleta-color-panel').forEach(function (panel) {
            panel.hidden = true;
        });
    }

    function initColorPickers() {
        var inputs = document.querySelectorAll('input.ruleta-color-source');
        inputs.forEach(attachColorPicker);
    }

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.ruleta-color-control') && !event.target.closest('.ruleta-color-panel')) {
            closeFallbackPanels();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeFallbackPanels();
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initColorPickers);
    } else {
        initColorPickers();
    }
})();

(function () {
    function resolveImageUrl(value) {
        if (!value) {
            return '';
        }

        if (value.indexOf('/static/') === 0 || value.indexOf('/media/') === 0) {
            return value;
        }

        if (value.indexOf('static/') === 0) {
            return '/static/' + value.replace(/^static\//, '');
        }

        return '/media/' + value;
    }

    function closeImagePickers() {
        document.querySelectorAll('.ruleta-image-picker-panel').forEach(function (panel) {
            panel.hidden = true;
        });
    }

    function positionImagePanel(picker) {
        var panel = picker._ruletaImagePanel;
        var selectedButton = picker.querySelector('.ruleta-image-selected');

        if (!panel || !selectedButton) {
            return;
        }

        var rect = selectedButton.getBoundingClientRect();
        var panelWidth = Math.min(Math.max(rect.width, 520), window.innerWidth - 16);
        var left = Math.min(Math.max(8, rect.left), window.innerWidth - panelWidth - 8);
        var top = rect.bottom + 6;
        var panelHeight = Math.min(420, window.innerHeight - top - 8);

        if (panelHeight < 240 && rect.top > window.innerHeight / 2) {
            panelHeight = Math.min(420, rect.top - 8);
            top = Math.max(8, rect.top - panelHeight - 6);
        }

        panel.style.left = left + 'px';
        panel.style.top = top + 'px';
        panel.style.width = panelWidth + 'px';
        panel.style.height = panelHeight + 'px';
    }

    function setSelectedImage(select, picker, value) {
        var url = resolveImageUrl(value);
        var image = picker.querySelector('.ruleta-image-selected-img');
        var path = picker.querySelector('.ruleta-image-selected-path');
        var panel = picker._ruletaImagePanel || picker;

        select.value = value;
        select.dispatchEvent(new Event('change', { bubbles: true }));

        if (url) {
            image.src = url;
            image.hidden = false;
            path.textContent = value;
        } else {
            image.removeAttribute('src');
            image.hidden = true;
            path.textContent = 'Mantener imagen actual o subir nueva';
        }

        panel.querySelectorAll('.ruleta-image-option').forEach(function (option) {
            option.setAttribute('aria-pressed', option.dataset.value === value ? 'true' : 'false');
        });
    }

    function filterImageOptions(picker, term) {
        var normalizedTerm = (term || '').trim().toLowerCase();
        var panel = picker._ruletaImagePanel || picker;
        var visibleCount = 0;

        panel.querySelectorAll('.ruleta-image-option').forEach(function (option) {
            var matches = !normalizedTerm || option.dataset.search.indexOf(normalizedTerm) !== -1;
            option.hidden = !matches;
            if (matches) {
                visibleCount += 1;
            }
        });

        var emptyState = panel.querySelector('.ruleta-image-empty');
        if (emptyState) {
            emptyState.hidden = visibleCount !== 0;
        }
    }

    function createImageOption(option, picker, select) {
        var value = option.value;
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'ruleta-image-option';
        button.dataset.value = value;
        button.dataset.search = (value + ' ' + option.textContent).toLowerCase();
        button.setAttribute('aria-pressed', 'false');

        if (value) {
            var image = document.createElement('img');
            image.src = resolveImageUrl(value);
            image.alt = '';
            image.loading = 'lazy';
            button.appendChild(image);
        } else {
            var placeholder = document.createElement('span');
            placeholder.className = 'ruleta-image-placeholder';
            placeholder.textContent = 'Sin imagen';
            button.appendChild(placeholder);
        }

        var label = document.createElement('span');
        label.textContent = option.textContent || value;
        button.appendChild(label);

        button.addEventListener('click', function () {
            setSelectedImage(select, picker, value);
            closeImagePickers();
        });

        return button;
    }

    function attachImagePicker(select) {
        if (select.dataset.imagePickerAttached === '1') {
            return;
        }

        select.dataset.imagePickerAttached = '1';
        select.classList.add('ruleta-image-source-hidden');

        var picker = document.createElement('div');
        picker.className = 'ruleta-image-picker';

        var selectedButton = document.createElement('button');
        selectedButton.type = 'button';
        selectedButton.className = 'ruleta-image-selected';

        var selectedImage = document.createElement('img');
        selectedImage.className = 'ruleta-image-selected-img';
        selectedImage.alt = '';
        selectedImage.hidden = true;

        var selectedPath = document.createElement('span');
        selectedPath.className = 'ruleta-image-selected-path';

        selectedButton.appendChild(selectedImage);
        selectedButton.appendChild(selectedPath);
        picker.appendChild(selectedButton);

        var panel = document.createElement('div');
        panel.className = 'ruleta-image-picker-panel';
        panel.hidden = true;

        var search = document.createElement('input');
        search.type = 'search';
        search.className = 'ruleta-image-search';
        search.placeholder = 'Buscar imagen...';
        search.autocomplete = 'off';
        panel.appendChild(search);

        var list = document.createElement('div');
        list.className = 'ruleta-image-options';
        Array.from(select.options).forEach(function (option) {
            list.appendChild(createImageOption(option, picker, select));
        });
        panel.appendChild(list);

        var emptyState = document.createElement('div');
        emptyState.className = 'ruleta-image-empty';
        emptyState.hidden = true;
        emptyState.textContent = 'Sin resultados';
        panel.appendChild(emptyState);

        select.insertAdjacentElement('afterend', picker);
        document.body.appendChild(panel);
        picker._ruletaImagePanel = panel;
        panel._ruletaImagePicker = picker;

        selectedButton.addEventListener('click', function () {
            var shouldOpen = panel.hidden;
            closeImagePickers();
            panel.hidden = !shouldOpen;
            if (shouldOpen) {
                search.value = '';
                filterImageOptions(picker, '');
                positionImagePanel(picker);
                search.focus();
            }
        });

        search.addEventListener('input', function () {
            filterImageOptions(picker, search.value);
        });

        select.addEventListener('change', function () {
            setSelectedImage(select, picker, select.value);
        });

        setSelectedImage(select, picker, select.value);
    }

    function initImagePickers() {
        document.querySelectorAll('select.ruleta-image-source').forEach(attachImagePicker);
    }

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.ruleta-image-picker') && !event.target.closest('.ruleta-image-picker-panel')) {
            closeImagePickers();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeImagePickers();
        }
    });

    window.addEventListener('resize', function () {
        document.querySelectorAll('.ruleta-image-picker-panel:not([hidden])').forEach(function (panel) {
            if (panel._ruletaImagePicker) {
                positionImagePanel(panel._ruletaImagePicker);
            }
        });
    });

    window.addEventListener('scroll', function () {
        document.querySelectorAll('.ruleta-image-picker-panel:not([hidden])').forEach(function (panel) {
            if (panel._ruletaImagePicker) {
                positionImagePanel(panel._ruletaImagePicker);
            }
        });
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initImagePickers);
    } else {
        initImagePickers();
    }
})();
