import screen_brightness_control as sbc
from monitorcontrol import get_monitors

print("--- SBC ---")
try:
    monitors = sbc.list_monitors_info()
    for m in monitors:
        print(m)
except Exception as e:
    print("SBC Error:", e)

print("--- MonitorControl ---")
try:
    for m in get_monitors():
        with m:
            print(m)
            try:
                print("Brightness:", m.get_luminance())
            except Exception as e:
                pass
            try:
                print("Contrast:", m.get_contrast())
            except Exception as e:
                pass
except Exception as e:
    print("MonitorControl Error:", e)
