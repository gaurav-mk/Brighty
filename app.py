import webview
import screen_brightness_control as sbc
from monitorcontrol import get_monitors
import requests
import threading
import time
from datetime import datetime
import ctypes
import pystray
from PIL import Image, ImageDraw
import json
import os
import sys
import winreg as reg
from astral.sun import elevation
from astral import LocationInfo

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

SETTINGS_FILE = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath("."), 'settings.json')

class BrightyAPI:
    def __init__(self):
        self.location_data = None
        self.weather_data = None
        self.monitors_cache = []
        self.settings = self.load_settings()
        
        # Start a background thread to fetch data and auto-adjust brightness
        self._bg_thread = threading.Thread(target=self._auto_adjust_loop, daemon=True)
        self._bg_thread.start()

    def add_to_startup(self):
        try:
            key = reg.HKEY_CURRENT_USER
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            registry_key = reg.OpenKey(key, key_path, 0, reg.KEY_ALL_ACCESS)
            
            if getattr(sys, 'frozen', False):
                # Running as an executable
                app_path = f'"{sys.executable}" --hidden'
            else:
                # Running as a script
                pythonw_path = sys.executable.replace("python.exe", "pythonw.exe")
                app_path = f'"{pythonw_path}" "{os.path.abspath(__file__)}" --hidden'
                
            reg.SetValueEx(registry_key, "ProjectBrighty", 0, reg.REG_SZ, app_path)
            reg.CloseKey(registry_key)
        except Exception as e:
            print("Startup reg error:", e)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_settings(self, settings):
        self.settings = settings
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print("Save settings error:", e)

    def fetch_location_weather(self):
        try:
            # Get Location from more precise ipapi.co
            headers = {'User-Agent': 'ProjectBrighty/1.0'}
            res = requests.get('https://ipapi.co/json/', headers=headers).json()
            if 'error' not in res:
                self.location_data = {
                    'city': res.get('city'),
                    'country': res.get('country_name'),
                    'lat': res.get('latitude'),
                    'lon': res.get('longitude'),
                    'timezone': res.get('timezone')
                }
                lat, lon = res.get('latitude'), res.get('longitude')
                
                # Get Weather & Sunrise/Sunset
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&daily=sunrise,sunset&timezone=auto"
                w_res = requests.get(weather_url).json()
                self.weather_data = w_res
        except Exception as e:
            print("Error fetching location/weather:", e)

    def get_info(self):
        if not self.location_data or not self.weather_data:
            self.fetch_location_weather()
            
        if self.location_data and self.weather_data:
            return {
                'city': self.location_data.get('city'),
                'country': self.location_data.get('country'),
                'temperature': self.weather_data['current']['temperature_2m'],
                'weather_code': self.weather_data['current']['weather_code'],
                'sunrise': self.weather_data['daily']['sunrise'][0],
                'sunset': self.weather_data['daily']['sunset'][0]
            }
        return {'error': 'Failed to load data'}

    def get_monitors(self):
        monitors = []
        # Get brightness using SBC
        sbc_monitors = sbc.list_monitors_info()
        for idx, m in enumerate(sbc_monitors):
            b_val = 50
            try:
                b_val = sbc.get_brightness(display=m['name'])[0]
            except:
                pass
                
            monitor_key = f"monitor_{idx}_{m['name']}"
            is_auto = self.settings.get(monitor_key, False)
            
            monitors.append({
                'id': idx,
                'name': m['name'],
                'brightness': b_val,
                'contrast': 50, # Default if monitorcontrol fails
                'auto_adjust': is_auto,
                'key': monitor_key
            })
            
        # Try to get contrast for external monitors
        try:
            for idx, mc in enumerate(get_monitors()):
                with mc:
                    c_val = mc.get_contrast()
                    if idx < len(monitors):
                        monitors[idx]['contrast'] = c_val
        except Exception as e:
            pass
            
        self.monitors_cache = monitors
        return monitors

    def set_brightness(self, monitor_id, val):
        if monitor_id < len(self.monitors_cache):
            name = self.monitors_cache[monitor_id]['name']
            sbc.set_brightness(val, display=name)

    def set_contrast(self, monitor_id, val):
        try:
            for idx, mc in enumerate(get_monitors()):
                if idx == monitor_id:
                    with mc:
                        mc.set_contrast(val)
        except Exception as e:
            pass

    def set_brightness_offset(self, val):
        self.settings['brightness_offset'] = val
        self.save_settings(self.settings)
        # Trigger immediate adjustment to apply new offset
        self.force_auto_adjust()

    def get_settings(self):
        return self.settings

    def set_monitor_auto(self, monitor_key, val):
        self.settings[monitor_key] = val
        self.save_settings(self.settings)

    def force_auto_adjust(self):
        # Trigger an immediate adjustment calculation
        threading.Thread(target=self._run_adjustment_logic, daemon=True).start()

    def minimize(self):
        webview.windows[0].minimize()

    def hide_app(self):
        webview.windows[0].hide()

    def show_app(self):
        webview.windows[0].show()

    def close_app(self):
        # We might want to actually close the whole app now that it's in the tray
        # But wait, usually the "close" button on the window just hides it
        self.hide_app()
        
    def quit_app(self):
        import os
        os._exit(0)
        
    def _run_adjustment_logic(self):
        if not self.location_data:
            return
        try:
            # Seamless daylight curve logic using sun elevation
            loc = LocationInfo(self.location_data['city'], self.location_data['country'], self.location_data['timezone'], self.location_data['lat'], self.location_data['lon'])
            alt = elevation(loc.observer, dateandtime=datetime.now())
            
            # Alt is > 0 when sun is above horizon. Peaks at ~60.
            if alt <= 0:
                target_brightness = 30
            else:
                # Map alt 0->60 to brightness 30->100
                target_brightness = 30 + (alt / 60.0) * 70
                target_brightness = int(min(100, max(30, target_brightness)))
                
            # If weather code implies cloudy/rainy/snow (codes > 50 in open-meteo), reduce brightness slightly
            if self.weather_data and self.weather_data['current']['weather_code'] > 50:
                target_brightness = int(max(10, target_brightness - 20))
                
            # Apply user offset from settings
            offset = self.settings.get('brightness_offset', 0)
            target_brightness = int(max(0, min(100, target_brightness + offset)))
                
            for m in self.monitors_cache:
                if m.get('auto_adjust', False) or self.settings.get(m['key'], False):
                    sbc.set_brightness(target_brightness, display=m['name'])
                    try:
                        webview.windows[0].evaluate_js(f"if(window.updateMonitorBrightness) window.updateMonitorBrightness({m['id']}, {target_brightness});")
                    except:
                        pass
        except Exception as e:
            print("Auto adjust logic error:", e)

    def _auto_adjust_loop(self):
        # Allow initial data fetch
        time.sleep(5) # Give it 5 seconds to settle
        while True:
            self._run_adjustment_logic()
            time.sleep(300) # Exactly 5 minutes between updates

if __name__ == '__main__':
    # Determine window size and position (bottom right)
    width = 380
    height = 480

    
    # Get screen size via ctypes
    user32 = ctypes.windll.user32
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    
    # Taskbar height approx 40px
    x = screen_width - width - 20
    y = screen_height - height - 60
    
    is_hidden = '--hidden' in sys.argv
    
    api = BrightyAPI()
    api.add_to_startup()
    
    window = webview.create_window(
        'Project Brighty',
        url=resource_path('ui/index.html'),
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        frameless=True,
        easy_drag=False,
        transparent=True,
        on_top=True,
        hidden=is_hidden
    )
    
    def load_tray_icon():
        # Load our new custom icon for the tray
        icon_path = resource_path(os.path.join('ui', 'icon.png'))
        if os.path.exists(icon_path):
            return Image.open(icon_path).resize((64, 64))
        # Fallback to generated image if not found
        image = Image.new('RGB', (64, 64), color=(15, 17, 26))
        dc = ImageDraw.Draw(image)
        dc.ellipse((16, 16, 48, 48), fill=(99, 102, 241))
        return image

    def on_clicked(icon, item):
        if str(item) == "Show/Hide":
            # pywebview doesn't easily expose visibility, so we just toggle by trying to show/hide
            # a simple state variable could also work
            pass

    def setup_tray():
        image = load_tray_icon()
        
        def show_action(icon, item):
            window.show()
            
        def hide_action(icon, item):
            window.hide()
            
        def exit_action(icon, item):
            icon.stop()
            import os
            os._exit(0)
            
        menu = pystray.Menu(
            pystray.MenuItem("Show Brighty", show_action, default=True),
            pystray.MenuItem("Hide Brighty", hide_action),
            pystray.MenuItem("Exit", exit_action)
        )
        icon = pystray.Icon("Brighty", image, "Brighty", menu)
        icon.run()

    def hide_from_taskbar(window):
        try:
            import ctypes
            # Set a unique AppUserModelID to prevent grouping with Python.exe
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Brighty.BrightnessWidget")
            except: pass
            
            # GWL_EXSTYLE constant
            GWL_EXSTYLE = -20
            # WS_EX_TOOLWINDOW: Hides from taskbar and prevents Alt-Tab entry
            WS_EX_TOOLWINDOW = 0x00000080
            # WS_EX_APPWINDOW: Forces onto taskbar
            WS_EX_APPWINDOW = 0x00040000
            
            user32 = ctypes.windll.user32
            hwnd = window.hwnd
            if hwnd:
                # 1. Hide the window to apply style changes
                user32.ShowWindow(hwnd, 0) 
                
                # 2. Modify styles: Add TOOLWINDOW, Remove APPWINDOW
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
                
                # 3. Show again
                user32.ShowWindow(hwnd, 5)
                
                # 4. Force a frame refresh
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027) # SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
        except Exception as e:
            print("Error hiding from taskbar:", e)

    # Start tray in a daemon thread
    threading.Thread(target=setup_tray, daemon=True).start()
    
    webview.start(hide_from_taskbar, window, debug=False, icon=resource_path('ui/icon.ico'))
