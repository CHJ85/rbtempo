# rbtempo: plugin to control Rhythmbox playback speed, pitch and tempo rate
# Copyright (C) 2015, 2025  BMerry and CHJ85
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from gi.repository import GObject, GLib, Gio, Gtk, RB, Peas, Gst
import math

def find_widget_by_name(root, name):
    """Recursively find the widget named `name` under root, returning
    `None` if it could not be found."""
    if not isinstance(root, Gtk.Widget):
        return None
    if isinstance(root, Gtk.Buildable) and Gtk.Buildable.get_name(root) == name:
        return root
    if isinstance(root, Gtk.Container):
        for child in root.get_children():
            ans = find_widget_by_name(child, name)
            if ans is not None:
                return ans
    return None

class RBTempoPlugin(GObject.Object, Peas.Activatable):
    """
    A Rhythmbox plugin to control playback tempo (speed), pitch, and rate.
    It uses the GStreamer 'pitch' element to modify the audio pipeline.
    """
    object = GObject.property(type=GObject.GObject)

    def get_shell(self):
        """Returns the main Rhythmbox shell object."""
        return self.object

    def get_player(self):
        """Returns the Rhythmbox shell player."""
        return self.get_shell().props.shell_player.props.player

    def get_toolbar(self):
        """Gets the widget for the main toolbar."""
        return find_widget_by_name(self.get_shell().props.window, 'main-toolbar')

    def property_changed(self, adj, user_data=None):
        """
        Callback for when any adjustment (tempo, pitch, speed) value changes.
        This ensures the GStreamer filter is present and updates its properties.
        """
        # Always ensure the filter is in the pipeline
        self.add_filter()

        if self.pitch_element is not None:
            self.pitch_element.props.tempo = self.tempo_adj.get_value() * 0.01 + 1.0
            self.pitch_element.props.pitch = math.pow(2.0, self.pitch_adj.get_value() / 12.0)
            self.pitch_element.props.rate = self.speed_adj.get_value() * 0.01 + 1.0

    def create_adj(self, value, lower, upper, step_increment, page_increment):
        """Helper function to create a Gtk.Adjustment."""
        adj = Gtk.Adjustment(value=value, lower=lower, upper=upper,
                             step_increment=step_increment, page_increment=page_increment)
        adj.connect('value-changed', self.property_changed)
        return adj

    def create_slider_widget(self, adj, spin_width_chars=4):
        """Creates a box containing a scale and spin button for a single control."""
        box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)

        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_size_request(100, -1)
        scale.set_draw_value(False)

        spin = Gtk.SpinButton.new(adj, 0, 0)
        spin.set_width_chars(spin_width_chars)

        box.pack_start(scale, True, True, 0)
        box.pack_start(spin, False, False, 0)
        return box

    def reset(self, button):
        """
        Resets all adjustments to their default values (0) and ensures the
        GStreamer filter properties are updated accordingly.
        """
        # Set all UI adjustments to their default value of 0.
        # The 'value-changed' signal will automatically trigger the property_changed method,
        # which will update the GStreamer filter's properties.
        self.tempo_adj.set_value(0)
        self.pitch_adj.set_value(0)
        self.speed_adj.set_value(0)

    def on_button_clicked(self, button, key):
        """Handler for the Tempo, Pitch, and Speed buttons.
        This changes the visible child of the Gtk.Stack."""
        self.dropdown_container.set_visible_child_name(key)

    def create_toolbox(self):
        """Creates the main UI widget to be inserted into the toolbar."""
        # --- Adjustments ---
        self.tempo_adj = self.create_adj(0, -50, 200, 5, 10)
        self.pitch_adj = self.create_adj(0, -12, 12, 1, 3)
        self.speed_adj = self.create_adj(0, -50, 200, 5, 10)

        # --- Main container - a vertical box to stack the buttons and the slider ---
        main_vbox = Gtk.Box.new(Gtk.Orientation.VERTICAL, 5)

        # --- Buttons for the controls ---
        button_hbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 5)

        tempo_button = Gtk.Button.new_with_label("Tempo")
        tempo_button.connect('clicked', self.on_button_clicked, 'tempo')

        pitch_button = Gtk.Button.new_with_label("Pitch")
        pitch_button.connect('clicked', self.on_button_clicked, 'pitch')

        speed_button = Gtk.Button.new_with_label("Speed")
        speed_button.connect('clicked', self.on_button_clicked, 'speed')

        button_hbox.pack_start(tempo_button, False, False, 0)
        button_hbox.pack_start(pitch_button, False, False, 0)
        button_hbox.pack_start(speed_button, False, False, 0)

        # --- Reset Button ---
        reset_button = Gtk.Button.new_from_icon_name('edit-undo-symbolic', Gtk.IconSize.BUTTON)
        reset_button.set_tooltip_text("Reset all controls")
        reset_button.connect('clicked', self.reset)
        button_hbox.pack_start(reset_button, False, False, 0)

        # --- Gtk.Stack for the slider widgets ---
        # This widget is specifically designed to hold multiple widgets and show only one at a time.
        self.dropdown_container = Gtk.Stack()
        self.dropdown_container.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.dropdown_container.set_transition_duration(250)

        # Create and add each slider to the stack with a unique name
        self.tempo_slider_box = self.create_slider_widget(self.tempo_adj, 4)
        self.dropdown_container.add_named(self.tempo_slider_box, 'tempo')
        self.pitch_slider_box = self.create_slider_widget(self.pitch_adj, 3)
        self.dropdown_container.add_named(self.pitch_slider_box, 'pitch')
        self.speed_slider_box = self.create_slider_widget(self.speed_adj, 4)
        self.dropdown_container.add_named(self.speed_slider_box, 'speed')

        # A dictionary to easily map button keys to their slider boxes (though not strictly necessary with Gtk.Stack)
        self.slider_map = {
            'tempo': self.tempo_slider_box,
            'pitch': self.pitch_slider_box,
            'speed': self.speed_slider_box
        }

        # Initially set the visible child to the tempo slider
        self.dropdown_container.set_visible_child_name('tempo')

        # Pack everything into the main vertical box
        main_vbox.pack_start(button_hbox, False, False, 0)
        main_vbox.pack_start(self.dropdown_container, False, False, 0)

        # --- Toolbar Item ---
        item = Gtk.ToolItem.new()
        item.set_margin_start(6)
        item.set_margin_end(6)
        item.set_margin_top(12)
        item.set_margin_bottom(12)
        item.add(main_vbox)

        # This is crucial: make sure everything is shown.
        item.show_all()
        return item

    def add_filter(self):
        """Add the 'pitch' filter to the GStreamer pipeline if not already present."""
        if self.pitch_element is None:
            self.pitch_element = Gst.ElementFactory.make("pitch", None)
            if self.pitch_element:
                self.get_player().add_filter(self.pitch_element)
            else:
                GLib.warning("RBTempoPlugin: Could not create GStreamer pitch element. Is gst-plugins-good installed?")

    def remove_filter(self):
        """Remove the 'pitch' filter from the GStreamer pipeline if it is present."""
        if self.pitch_element is not None:
            self.get_player().remove_filter(self.pitch_element)
            self.pitch_element = None

    def do_activate(self):
        """Plugin activation callback."""
        Gst.init(None)
        self.pitch_element = None
        self.toolbox = None
        self.add_filter() # Ensure filter is present on activation

        try:
            toolbar = self.get_toolbar()
            if toolbar:
                self.toolbox = self.create_toolbox()
                toolbar.insert(self.toolbox, 2)
            else:
                GLib.warning("RBTempoPlugin: Could not find Rhythmbox main toolbar.")
        except Exception as e:
            GLib.warning(f"RBTempoPlugin: Failed to activate UI: {e}")

    def do_deactivate(self):
        """Plugin deactivation callback."""
        self.remove_filter()
        if self.toolbox:
            try:
                toolbar = self.get_toolbar()
                if toolbar and self.toolbox.get_parent():
                    toolbar.remove(self.toolbox)
                elif not toolbar:
                    GLib.warning("RBTempoPlugin: Could not find main toolbar during deactivation.")
            except Exception as e:
                GLib.warning(f"RBTempoPlugin: Failed to deactivate UI: {e}")

        self.toolbox = None
        self.pitch_element = None
