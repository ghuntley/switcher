#!/usr/bin/env python
import pygtk
pygtk.require('2.0')
import sys
import wnck
import gtk
import gnomeapplet
import time


def switcher_factory(applet, iid):
    switcher = Switcher(applet)
    return gtk.TRUE

class Switcher(object):
    def __init__(self, applet):
        self.number = 0
        
        self.applet = applet
        self.container = None

        self.scr = wnck.screen_get_default()

        while gtk.events_pending():
            gtk.main_iteration()

        self.initialize()

        if self.is_virtual:
            self.scr.connect('viewports-changed', self.viewports_changed)
        else:
            self.scr.connect('active-workspace-changed', self.active_workspace_changed)
        self.scr.connect('active-window-changed', self.active_window_changed)
        self.scr.connect('window-opened', self.window_opened)
        self.scr.connect('window-closed', self.window_closed)

    def _get_num_desktops(self):
        if self.use_viewports:
            return self.num_viewports
        else:
            return self.num_workspaces
    num_desktops = property(_get_num_desktops)

    def _get_active_desktop(self):
        ws = self.scr.get_active_workspace()
        if self.use_viewports:
            return ws.get_viewport_x()/self.scr_width
        else:
            return ws.get_number()
    active_desktop = property(_get_active_desktop)

    def get_desktop_num_for_win(self, win):
        if self.use_viewports:
            ws = self.scr.get_active_workspace()
            x = ws.get_viewport_x()

            offset = x/self.scr_width
            x, y, width, height = win.get_geometry()
            num = (x+offset*self.scr_width)/self.scr_width
            if num < 0 or num >= self.num_desktops:
                # Eek
                return 0
            return num
        else:
            ws = win.get_workspace()
            if not ws:
                # None for sticky windows, docks, desktop, etc.
                return self.scr.get_active_workspace().get_number()
            return ws.get_number()

    def switch_to_desktop(self, number):
        if self.use_viewports:
            # move to correct desktop
            x = self.scr_width * number
            self.scr.move_viewport(x, 0)

        else:
            timestamp = int(time.time())
            self.scr.get_workspace(number).activate(timestamp)

    ###

    def clear(self):
        if self.container:
            self.applet.remove(self.container)

        self.container = gtk.HandleBox()
        self.toolbar = gtk.Toolbar()
        self.toolbar.set_show_arrow(False)
        self.toolbar.set_style(gtk.TOOLBAR_ICONS)

        self.container.add(self.toolbar)
        self.applet.add(self.container)

        self.desktops = []

        self.desktop_button_group = None
        self.app_button_group = None

        # terrible hacks because I can't otherwise differentiate between when
        # buttons were actually clicked by the user and when we toggled them
        # through code
        self.desktop_button_not_clicked = False
        self.last_desktop_button = None
        self.last_app_button = None

    def initialize(self):
        self.number += 1
        #print "initialize", self.number
        
        self.scr_width = self.scr.get_width()
        self.scr_height = self.scr.get_height()

        ws = self.scr.get_active_workspace()

        self.is_virtual = ws.is_virtual()
        self.num_workspaces = self.scr.get_workspace_count()
        self.use_viewports = self.is_virtual and self.num_workspaces == 1

        if self.use_viewports:
            # the compiz path: 1 workspace and it is virtual
            ws_width = ws.get_width()
            ws_height = ws.get_height()
            self.num_viewports = ws_width/self.scr_width
        else:
            # the metacity path: multiple workspaces or not virtual
            self.num_viewports = 0

        self.clear()

        # show desktop button
        self.show_desktop_button = gtk.RadioToolButton()
        #self.show_desktop_button.set_icon_widget(gtk.Label("D"))
        image = gtk.Image()
        image.set_from_icon_name('desktop', gtk.ICON_SIZE_MENU)
        self.show_desktop_button.set_icon_widget(image)
        self.app_button_group = self.show_desktop_button
        self.toolbar.insert(self.show_desktop_button, 0)
        self.show_desktop_button.connect("clicked", self.click_show_desktop_button)
        self.show_desktop_button.set_tooltip_text("Toggle Show Desktop")

        # desktops
        for number in range(self.num_desktops):
            desktop = Desktop(self, number)
            self.desktops.append(desktop)
            if not self.desktop_button_group:
                self.desktop_button_group = desktop.button

        # apps and windows
        for win in self.scr.get_windows():
            if win.get_window_type().value_name != "WNCK_WINDOW_NORMAL":
                continue

            win_app = win.get_application()
            pid = win_app.get_pid()
            desktop_num = self.get_desktop_num_for_win(win)
            desktop = self.desktops[desktop_num]

            # add the app if it is not on this window's desktop yet
            app = desktop.get_app_by_pid(pid)
            if not app:
                is_active = win.is_active()
                app = App(self, desktop, win_app, is_active)
                desktop.apps.append(app)

            # add the window
            app.windows.append(win)
            win.connect("geometry-changed", app.win_geometry_changed)

        self.applet.show_all()

    ###

    def active_workspace_changed(self, src, ws):
        # TODO: optimise
        self.initialize()

    def viewports_changed(self, scr):
        # TODO: optimise
        self.initialize()

    def active_window_changed(self, scr, win):
        # for some reason win is the _old_ window
        win = scr.get_active_window()
        if not win:
            # for some reason we get the event twice,
            # every other time win is None
            return

        app = None
        if win.get_window_type().value_name == "WNCK_WINDOW_NORMAL":
            desktop_num = self.get_desktop_num_for_win(win)
            desktop = self.desktops[desktop_num]
            win_app = win.get_application()
            pid = win_app.get_pid()
            app = desktop.get_app_by_pid(pid)

        if app:
            # change the image (this is probably inefficient)
            #pixbuf = win.get_mini_icon()
            #image = gtk.Image()
            #image.set_from_pixbuf(pixbuf)
            #app.button.set_icon_widget(image)

            self.desktop_button_not_clicked = True # prevent event
            self.last_app_button = app.button
            app.button.set_active(True)
            self.desktop_button_not_clicked = False

        else:
            # no app is selected, so activate the desktop button
            self.desktop_button_not_clicked = True # prevent event
            self.last_app_button = self.show_desktop_button
            self.show_desktop_button.set_active(True)
            self.desktop_button_not_clicked = False

    def window_opened(self, scr, win):
        # TODO: optimise
        self.initialize()

    def window_closed(self, scr, win):
        # TODO: optimise
        self.initialize()

    def click_show_desktop_button(self, button):
        if self.desktop_button_not_clicked:
            # clicked got triggered because we changed its state with code
            self.desktop_button_not_clicked = False
            return

        # toggle show desktop
        showing = self.scr.get_showing_desktop()
        self.scr.toggle_showing_desktop(not showing)

        if not button.get_active():
            # the button is already the active one
            return

        for win in self.scr.get_windows():
            if win.get_window_type().value_name == "WNCK_WINDOW_DESKTOP":
                timestamp = int(time.time())
                win.activate(timestamp)
                break

class Desktop(object):
    def __init__(self, switcher, number):
        self.apps = []
        self.switcher = switcher
        self.number = number

        text = str(number+1)
        self.button = gtk.RadioToolButton()
        label = gtk.Label(text)
        label.set_markup('<b>'+text+'</b>')
        self.button.set_icon_widget(label)
        self.button.set_tooltip_text('Desktop '+text)
        if switcher.desktop_button_group:
            self.button.set_group(switcher.desktop_button_group)
        if number == switcher.active_desktop:
            switcher.last_desktop_button = self.button
            self.button.set_active(True)
        switcher.toolbar.insert(self.button, -1)

        self.button.connect("clicked", self.click_desktop_button)

    def get_app_by_pid(self, pid):
        for app in self.apps:
            if app.pid == pid:
                return app
        return None

    def click_desktop_button(self, button):
        if not button.get_active():
            # the button is already the active one
            return

        if button == self.switcher.last_desktop_button:
            # the user didn't click the button - it was activated from elsewhere
            return

        self.switcher.switch_to_desktop(self.number)

class App(object):
    def __init__(self, switcher, desktop, app, is_active):
        self.windows = []
        self.switcher = switcher
        self.desktop = desktop
        self.pid = app.get_pid()

        pixbuf = app.get_mini_icon()

        self.button = gtk.RadioToolButton()
        self.button.set_group(switcher.app_button_group)
        image = gtk.Image()
        image.set_from_pixbuf(pixbuf)
        self.button.set_icon_widget(image)
        if is_active:
            switcher.last_desktop_button = self.button
            self.switcher.desktop_button_not_clicked = True # prevent event
            self.button.set_active(True)
            self.switcher.desktop_button_not_clicked = False
        self.button.set_tooltip_text(app.get_name())

        if desktop.number == switcher.num_desktops-1:
            pos = -1
        else:
            children = switcher.toolbar.get_children()
            db = switcher.desktops[desktop.number+1].button
            pos = children.index(db)

        switcher.toolbar.insert(self.button, pos)

        self.button.connect("clicked", self.click_app_button)

    def get_main_window(self):
        for win in self.windows:
            if win.get_window_type().value_name == "WNCK_WINDOW_NORMAL":
                return win
        return self.windows[0] # fallback

    def click_app_button(self, button):
        if not button.get_active():
            # the button is already the active one
            return

        if button == self.switcher.last_app_button:
            # the user didn't click the button - it was activated from elsewhere
            return

        self.switcher.switch_to_desktop(self.desktop.number)

        # activate the window
        timestamp = int(time.time())
        self.get_main_window().activate(timestamp)

    def win_geometry_changed(self, win):
        if not self.switcher.is_virtual:
            # non-virtual desktops don't need to calculate the viewport
            return

        if win.is_pinned():
            # pinned windows completely miss this up
            return

        ws = self.switcher.scr.get_active_workspace()
        if not win.is_in_viewport(ws):
            # some compiz weirdness
            return

        win_desktop_num = self.switcher.get_desktop_num_for_win(win)
        if win_desktop_num != self.switcher.active_desktop:
            # TODO: optimise            
            self.switcher.initialize()

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '-d': # debugging
        print "="*80
        main_window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        main_window.set_title("Desktop/App Switcher")
        main_window.connect("destroy", gtk.main_quit)
        app = gnomeapplet.Applet()
        switcher_factory(app, None)
        app.reparent(main_window)
        main_window.show_all()
        #main_window.set_size_request(-1, 29)
        gtk.main()
        sys.exit()
    else:
        gnomeapplet.bonobo_factory("OAFIID:GNOME_SwitcherApplet_Factory",
                                     gnomeapplet.Applet.__gtype__,
                                     "Desktop/App Switcher", "0",
                                     switcher_factory)


if __name__ == "__main__":
    main()
