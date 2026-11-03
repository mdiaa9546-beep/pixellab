import os
import time
import cv2
import numpy as np

from kivy.app import App
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

IS_ANDROID = platform == "android"

if not IS_ANDROID:
    # Desktop only: phones ignore these and use the full screen.
    Window.size = (1100, 760)
    Window.minimum_width = 850
    Window.minimum_height = 600
Window.clearcolor = (0.055, 0.065, 0.09, 1)

BG = (0.055, 0.065, 0.09, 1)
PANEL = (0.09, 0.105, 0.14, 1)
BUTTON = (0.14, 0.17, 0.23, 1)
ACCENT = (0.1, 0.65, 0.95, 1)
WHITE = (0.92, 0.94, 0.98, 1)
MUTED = (0.6, 0.65, 0.73, 1)


class HistogramPlot(Widget):
    """Draw a simple grayscale intensity histogram using Kivy canvas."""

    def __init__(self, histogram, **kwargs):
        super().__init__(**kwargs)
        self.histogram = histogram
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def redraw(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        values = self.histogram.astype(np.float32).flatten()
        if values.size == 0:
            return
        max_value = max(float(values.max()), 1.0)
        padding = dp(18)
        plot_width = max(1, self.width - 2 * padding)
        plot_height = max(1, self.height - 2 * padding)
        points = []
        for index, value in enumerate(values):
            x = self.x + padding + (index / max(1, len(values) - 1)) * plot_width
            y = self.y + padding + (float(value) / max_value) * plot_height
            points.extend([x, y])

        with self.canvas:
            Color(0.28, 0.75, 1.0, 1)
            Line(points=points, width=1.2)
            Color(0.55, 0.62, 0.72, 0.65)
            Line(points=[
                self.x + padding, self.y + padding,
                self.x + padding + plot_width, self.y + padding
            ], width=1)
            Line(points=[
                self.x + padding, self.y + padding,
                self.x + padding, self.y + padding + plot_height
            ], width=1)


class PixelLabApp(App):
    def build(self):
        self.original = None
        self.current = None
        self.filter_name = "Original"
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.history = []
        self.zoom_factor = 1.0

        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))

        header = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(12))
        header.add_widget(Label(
            text="[b]PIXELLAB[/b]", markup=True, font_size="28sp",
            color=ACCENT, halign="left"
        ))
        header.add_widget(Label(
            text="IMAGE PROCESSING STUDIO", font_size="12sp", color=MUTED
        ))
        root.add_widget(header)

        main = BoxLayout(
            spacing=dp(14),
            orientation="vertical" if IS_ANDROID else "horizontal"
        )

        preview_panel = BoxLayout(
            orientation="vertical", padding=dp(12), spacing=dp(10),
            size_hint=((1, 0.42) if IS_ANDROID else (0.67, 1))
        )
        with preview_panel.canvas.before:
            Color(*PANEL)
            self.preview_bg = RoundedRectangle(
                pos=preview_panel.pos, size=preview_panel.size, radius=[dp(12)]
            )
        preview_panel.bind(pos=self._update_preview_bg, size=self._update_preview_bg)

        self.preview_area = BoxLayout()
        self.preview = Image(allow_stretch=True, keep_ratio=True)
        self.placeholder = Label(
            text="[b]Your creative space[/b]\n\nOpen an image to get started",
            markup=True, font_size="20sp", color=MUTED, halign="center"
        )
        self.preview_area.add_widget(self.placeholder)
        preview_panel.add_widget(self.preview_area)

        self.status = Label(
            text="Ready | No image selected", size_hint_y=None,
            height=dp(30), color=MUTED, font_size="12sp"
        )
        preview_panel.add_widget(self.status)
        main.add_widget(preview_panel)

        controls = BoxLayout(
            orientation="vertical", padding=dp(12), spacing=dp(7), size_hint_x=0.33
        )
        with controls.canvas.before:
            Color(*PANEL)
            self.controls_bg = RoundedRectangle(
                pos=controls.pos, size=controls.size, radius=[dp(12)]
            )
        controls.bind(pos=self._update_controls_bg, size=self._update_controls_bg)

        controls.add_widget(self._heading("IMAGE"))
        self._add_button(controls, "Choose Image", self.choose_image, ACCENT)
        controls.add_widget(self._heading("FILTERS"))

        filter_rows = [
            [("Original", "Original"), ("Grayscale", "Grayscale")],
            [("Negative", "Negative"), ("Sepia", "Sepia")],
            [("Warm", "Warm"), ("Cool", "Cool")],
            [("Gaussian Blur", "Blur"), ("Edge Detection", "Edges")],
        ]
        for items in filter_rows:
            row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
            for caption, value in items:
                button = Button(
                    text=caption, background_normal="", background_color=BUTTON,
                    color=WHITE, font_size="12sp"
                )
                button.bind(on_release=lambda instance, f=value: self.apply_filter(f))
                row.add_widget(button)
            controls.add_widget(row)

        controls.add_widget(self._heading("TRANSFORM"))
        transform_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        for caption, callback in [
            ("Rotate 90°", self.rotate_image),
            ("Flip H", self.flip_horizontal),
            ("Flip V", self.flip_vertical),
        ]:
            button = Button(
                text=caption, background_normal="", background_color=BUTTON,
                color=WHITE, font_size="11sp"
            )
            button.bind(on_release=callback)
            transform_row.add_widget(button)
        controls.add_widget(transform_row)

        edit_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        for caption, callback in [
            ("Crop", self.open_crop_dialog),
            ("Undo", self.undo),
        ]:
            button = Button(
                text=caption, background_normal="", background_color=BUTTON,
                color=WHITE, font_size="12sp"
            )
            button.bind(on_release=callback)
            edit_row.add_widget(button)
        controls.add_widget(edit_row)
        self._add_button(controls, "Show Histogram", self.show_histogram, BUTTON)

        controls.add_widget(self._heading("ADJUSTMENTS"))
        self.brightness_slider = self._add_slider(controls, "Brightness", -100, 100, 0)
        self.contrast_slider = self._add_slider(controls, "Contrast", 0.2, 2.5, 1)
        self.saturation_slider = self._add_slider(controls, "Saturation", 0, 2.5, 1)
        self.zoom_slider = self._add_slider(controls, "Preview Zoom", 0.5, 1.5, 1.0)
        self.zoom_slider.bind(value=self.on_zoom)

        for slider in (self.brightness_slider, self.contrast_slider, self.saturation_slider):
            slider.bind(value=self.on_adjustment)

        self._add_button(controls, "Reset All", self.reset_all, BUTTON)
        self._add_button(controls, "Save Edited Image", self.save_image, ACCENT)

        # The controls are taller than the available window after adding features.
        # Put them in a ScrollView so "Choose Image" and the lower buttons stay reachable.
        controls.size_hint_y = None
        controls.bind(minimum_height=controls.setter("height"))
        controls.size_hint_x = 1

        controls_scroll = ScrollView(
            size_hint=((1, 0.58) if IS_ANDROID else (0.33, 1)),
            do_scroll_x=False,
            bar_width=dp(5),
            scroll_type=["bars", "content"],
        )
        controls_scroll.add_widget(controls)
        main.add_widget(controls_scroll)
        root.add_widget(main)
        root.add_widget(Label(
            text="PixelLab | Python + OpenCV", size_hint_y=None,
            height=dp(22), color=MUTED, font_size="11sp"
        ))
        return root

    def on_start(self):
        if IS_ANDROID:
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                    "android.permission.READ_MEDIA_IMAGES",
                ])
            except Exception as exc:
                self.status.text = f"Permission request failed: {exc}"

    def _pictures_dir(self):
        if IS_ANDROID:
            try:
                from android.storage import primary_external_storage_path
                base = primary_external_storage_path()
            except Exception:
                base = "/storage/emulated/0"
            return os.path.join(base, "Pictures")
        return os.path.expanduser("~/Pictures")

    def _start_dir(self):
        folder = self._pictures_dir()
        if os.path.isdir(folder):
            return folder
        return os.path.dirname(folder) if os.path.isdir(os.path.dirname(folder)) else os.path.expanduser("~")

    @staticmethod
    def _limit_size(image, max_side=1600):
        # Phone photos are huge; undo history keeps copies, so shrink to save memory.
        height, width = image.shape[:2]
        biggest = max(height, width)
        if biggest <= max_side:
            return image
        scale = max_side / biggest
        return cv2.resize(image, (int(width * scale), int(height * scale)),
                          interpolation=cv2.INTER_AREA)

    def _save_android(self):
        folder = os.path.join(self._pictures_dir(), "PixelLab")
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, time.strftime("edited_%Y%m%d_%H%M%S.png"))
            ok = cv2.imwrite(path, self.current)
        except Exception as exc:
            self.status.text = f"Could not save: {exc}"
            return
        if not ok:
            self.status.text = "Could not save image"
            return
        try:  # make the image appear in the Gallery
            from jnius import autoclass
            scanner = autoclass("android.media.MediaScannerConnection")
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            scanner.scanFile(activity, [path], None, None)
        except Exception:
            pass
        self.status.text = f"Saved: {path}"

    def _update_preview_bg(self, widget, *_):
        self.preview_bg.pos = widget.pos
        self.preview_bg.size = widget.size

    def _update_controls_bg(self, widget, *_):
        self.controls_bg.pos = widget.pos
        self.controls_bg.size = widget.size

    def _heading(self, text):
        return Label(
            text=f"[b]{text}[/b]", markup=True, size_hint_y=None,
            height=dp(23), color=ACCENT, halign="left", font_size="13sp"
        )

    def _add_button(self, parent, text, callback, color):
        button = Button(
            text=text, size_hint_y=None, height=dp(40),
            background_normal="", background_color=color,
            color=WHITE, font_size="13sp"
        )
        button.bind(on_release=callback)
        parent.add_widget(button)
        return button

    def _add_slider(self, parent, name, minimum, maximum, initial):
        label = Label(
            text=f"{name}: {initial}", size_hint_y=None, height=dp(20),
            color=WHITE, font_size="12sp"
        )
        slider = Slider(
            min=minimum, max=maximum, value=initial,
            size_hint_y=None, height=dp(36)
        )
        slider.value_label = label
        slider.name = name
        slider.bind(value=self._update_slider_label)
        parent.add_widget(label)
        parent.add_widget(slider)
        return slider

    def _update_slider_label(self, slider, value):
        shown = f"{value:.2f}" if slider.name != "Brightness" else str(int(value))
        slider.value_label.text = f"{slider.name}: {shown}"

    def _save_history(self):
        if self.original is None:
            return
        self.history.append({
            "original": self.original.copy(),
            "filter_name": self.filter_name,
            "rotation": self.rotation,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "brightness": self.brightness_slider.value,
            "contrast": self.contrast_slider.value,
            "saturation": self.saturation_slider.value,
        })
        if len(self.history) > 30:
            self.history.pop(0)

    def undo(self, *_):
        if not self.history:
            self.status.text = "Nothing to undo"
            return
        state = self.history.pop()
        self.original = state["original"]
        self.filter_name = state["filter_name"]
        self.rotation = state["rotation"]
        self.flip_h = state["flip_h"]
        self.flip_v = state["flip_v"]
        self.brightness_slider.value = state["brightness"]
        self.contrast_slider.value = state["contrast"]
        self.saturation_slider.value = state["saturation"]
        self.render_image()
        self.status.text = "Last edit undone"

    def on_zoom(self, slider, value):
        self.zoom_factor = float(value)
        # Zoom affects the preview display only; saved image dimensions stay unchanged.
        if self.current is not None:
            self.show_image(self.current)

    def open_crop_dialog(self, *_):
        if self.original is None:
            self.status.text = "Choose an image first"
            return

        height, width = self.original.shape[:2]
        layout = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        layout.add_widget(Label(
            text=f"Crop image: {width} x {height}\nSet the crop area as percentages",
            size_hint_y=None, height=dp(48), color=WHITE
        ))

        x_slider = self._add_slider(layout, "Left (%)", 0, 90, 0)
        y_slider = self._add_slider(layout, "Top (%)", 0, 90, 0)
        w_slider = self._add_slider(layout, "Width (%)", 10, 100, 100)
        h_slider = self._add_slider(layout, "Height (%)", 10, 100, 100)

        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        popup = Popup(title="Crop Image", content=layout, size_hint=(0.8, 0.8))

        def apply_crop(*_):
            self._save_history()
            x = int(width * x_slider.value / 100)
            y = int(height * y_slider.value / 100)
            crop_w = int(width * w_slider.value / 100)
            crop_h = int(height * h_slider.value / 100)
            crop_w = min(crop_w, width - x)
            crop_h = min(crop_h, height - y)
            if crop_w < 1 or crop_h < 1:
                self.status.text = "Invalid crop area"
                return
            self.original = self.original[y:y + crop_h, x:x + crop_w].copy()
            self.filter_name = "Original"
            self.rotation = 0
            self.flip_h = False
            self.flip_v = False
            self._reset_sliders()
            self.render_image()
            self.status.text = f"Cropped to {crop_w} x {crop_h}"
            popup.dismiss()

        apply_button = Button(text="Apply Crop")
        apply_button.bind(on_release=apply_crop)
        cancel_button = Button(text="Cancel")
        cancel_button.bind(on_release=popup.dismiss)
        actions.add_widget(apply_button)
        actions.add_widget(cancel_button)
        layout.add_widget(actions)
        popup.open()

    def choose_image(self, *_):
        chooser = FileChooserIconView(
            path=self._start_dir(),
            filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.PNG", "*.JPG", "*.JPEG"]
        )
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        layout.add_widget(chooser)
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        popup = Popup(title="Choose an Image", content=layout, size_hint=(0.9, 0.9))

        def open_selected(*_):
            if not chooser.selection:
                self.status.text = "Select an image first"
                return
            path = chooser.selection[0]
            image = cv2.imread(path)
            if image is None:
                self.status.text = "Could not open this image"
                return
            self.history.clear()
            self.original = self._limit_size(image)
            self.filter_name = "Original"
            self.rotation = 0
            self.flip_h = False
            self.flip_v = False
            self._reset_sliders()
            self.render_image()
            self.status.text = os.path.basename(path)
            popup.dismiss()

        open_button = Button(text="Open")
        open_button.bind(on_release=open_selected)
        cancel_button = Button(text="Cancel")
        cancel_button.bind(on_release=popup.dismiss)
        actions.add_widget(open_button)
        actions.add_widget(cancel_button)
        layout.add_widget(actions)
        popup.open()

    def _reset_sliders(self):
        self.brightness_slider.value = 0
        self.contrast_slider.value = 1
        self.saturation_slider.value = 1

    def apply_filter(self, name):
        if self.original is None:
            self.status.text = "Choose an image first"
            return
        self._save_history()
        self.filter_name = name
        self.render_image()

    def on_adjustment(self, *_):
        if self.original is not None:
            self.render_image()

    def render_image(self):
        if self.original is None:
            return
        img = self.original.copy()

        if self.filter_name == "Grayscale":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        elif self.filter_name == "Negative":
            img = 255 - img
        elif self.filter_name == "Sepia":
            matrix = np.array([
                [0.272, 0.534, 0.131],
                [0.349, 0.686, 0.168],
                [0.393, 0.769, 0.189]
            ], dtype=np.float32)
            img = np.clip(cv2.transform(img, matrix), 0, 255).astype(np.uint8)
        elif self.filter_name == "Warm":
            img = img.astype(np.float32)
            img[:, :, 2] *= 1.15
            img[:, :, 0] *= 0.90
            img = np.clip(img, 0, 255).astype(np.uint8)
        elif self.filter_name == "Cool":
            img = img.astype(np.float32)
            img[:, :, 0] *= 1.15
            img[:, :, 2] *= 0.90
            img = np.clip(img, 0, 255).astype(np.uint8)
        elif self.filter_name == "Blur":
            img = cv2.GaussianBlur(img, (11, 11), 0)
        elif self.filter_name == "Edges":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            img = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

        img = cv2.convertScaleAbs(
            img, alpha=float(self.contrast_slider.value),
            beta=float(self.brightness_slider.value)
        )

        if self.filter_name != "Grayscale" and self.filter_name != "Edges":
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] *= float(self.saturation_slider.value)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
            img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        if self.rotation:
            turns = (self.rotation // 90) % 4
            if turns == 1:
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            elif turns == 2:
                img = cv2.rotate(img, cv2.ROTATE_180)
            elif turns == 3:
                img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self.flip_h:
            img = cv2.flip(img, 1)
        if self.flip_v:
            img = cv2.flip(img, 0)

        self.current = img
        self.show_image(img)
        self.status.text = (
            f"{self.filter_name} | Brightness {int(self.brightness_slider.value)}"
        )

    def show_image(self, img):
        if len(img.shape) == 2:
            rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        texture = Texture.create(size=(width, height), colorfmt="rgb")
        texture.blit_buffer(rgb.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        texture.flip_vertical()
        self.preview.texture = texture
        self.preview_area.clear_widgets()
        self.preview.size_hint = (self.zoom_factor, self.zoom_factor)
        self.preview_area.add_widget(self.preview)

    def rotate_image(self, *_):
        if self.original is None:
            self.status.text = "Choose an image first"
            return
        self._save_history()
        self.rotation = (self.rotation + 90) % 360
        self.render_image()
        self.status.text = f"Rotated {self.rotation} degrees"

    def flip_horizontal(self, *_):
        if self.original is None:
            self.status.text = "Choose an image first"
            return
        self._save_history()
        self.flip_h = not self.flip_h
        self.render_image()
        self.status.text = "Horizontal flip applied" if self.flip_h else "Horizontal flip removed"

    def flip_vertical(self, *_):
        if self.original is None:
            self.status.text = "Choose an image first"
            return
        self._save_history()
        self.flip_v = not self.flip_v
        self.render_image()
        self.status.text = "Vertical flip applied" if self.flip_v else "Vertical flip removed"

    def reset_all(self, *_):
        if self.original is None:
            self.status.text = "Choose an image first"
            return
        self._save_history()
        self.filter_name = "Original"
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self._reset_sliders()
        self.zoom_slider.value = 1.0
        self.render_image()
        self.status.text = "All adjustments reset"

    def show_histogram(self, *_):
        if self.original is None:
            self.status.text = "Choose an image first"
            return

        # Show the histogram of the currently displayed edited image.
        image = self.current if self.current is not None else self.original
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        histogram = cv2.calcHist([gray], [0], None, [256], [0, 256])

        content = BoxLayout(
            orientation="vertical", padding=dp(12), spacing=dp(8)
        )
        content.add_widget(Label(
            text="Grayscale Histogram\nX-axis: intensity (0 = black, 255 = white)\nY-axis: number of pixels",
            size_hint_y=None, height=dp(65), color=WHITE,
            halign="center", valign="middle"
        ))
        plot = HistogramPlot(
            histogram, size_hint=(1, 1)
        )
        content.add_widget(plot)
        close_button = Button(
            text="Close", size_hint_y=None, height=dp(42)
        )
        popup = Popup(
            title="PixelLab — Histogram",
            content=content, size_hint=(0.82, 0.72)
        )
        close_button.bind(on_release=popup.dismiss)
        content.add_widget(close_button)
        popup.open()

    def save_image(self, *_):
        if self.current is None:
            self.status.text = "Choose an image first"
            return

        if IS_ANDROID:
            self._save_android()
            return

        chooser = FileChooserIconView(
            path=self._pictures_dir(), dirselect=True
        )
        layout = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        layout.add_widget(chooser)
        layout.add_widget(Label(
            text="The edited image will be saved as edited_image.png",
            size_hint_y=None, height=dp(30)
        ))
        actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        popup = Popup(title="Save Edited Image", content=layout, size_hint=(0.9, 0.9))

        def save(*_):
            folder = chooser.path
            if not os.path.isdir(folder):
                self.status.text = "Choose a valid folder"
                return
            path = os.path.join(folder, "edited_image.png")
            if cv2.imwrite(path, self.current):
                self.status.text = f"Saved: {path}"
                popup.dismiss()
            else:
                self.status.text = "Could not save image"

        save_button = Button(text="Save")
        save_button.bind(on_release=save)
        cancel_button = Button(text="Cancel")
        cancel_button.bind(on_release=popup.dismiss)
        actions.add_widget(save_button)
        actions.add_widget(cancel_button)
        layout.add_widget(actions)
        popup.open()


if __name__ == "__main__":
    PixelLabApp().run()
