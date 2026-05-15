// Wait for pywebview to be ready
window.addEventListener('pywebviewready', function() {
    initApp();
});

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

window.updateMonitorBrightness = (monitorId, val) => {
    const bSlider = document.getElementById(`b-slider-${monitorId}`);
    const bVal = document.getElementById(`b-val-${monitorId}`);
    if (bSlider && bVal) {
        bSlider.value = val;
        bVal.textContent = `${val}%`;
        bSlider.style.setProperty('--val', `${val}%`);
    }
};

// For development in browser without pywebview
if (typeof window.pywebview === 'undefined') {
    setTimeout(() => {
        if (typeof window.pywebview === 'undefined') {
            console.log("Mocking pywebview for browser testing...");
            window.pywebview = {
                api: {
                    get_info: async () => ({
                        city: "Test City", country: "TC", temperature: 22, weather_code: 0,
                        sunrise: "2023-01-01T06:00", sunset: "2023-01-01T18:00", auto_adjust: true
                    }),
                    get_monitors: async () => ([
                        { id: 0, name: "Internal Display", brightness: 80, contrast: 50 },
                        { id: 1, name: "External Monitor", brightness: 60, contrast: 70 }
                    ]),
                    set_brightness: async (id, val) => console.log(`Set brightness ${id} to ${val}`),
                    set_contrast: async (id, val) => console.log(`Set contrast ${id} to ${val}`),
                    set_auto_adjust: async (val) => console.log(`Auto adjust: ${val}`),
                    minimize: async () => console.log("Minimize"),
                    close_app: async () => console.log("Close")
                }
            };
            initApp();
        }
    }, 1000);
}

async function initApp() {
    const api = window.pywebview.api;

    // Window Controls
    document.getElementById('close-btn').addEventListener('click', () => {
        api.close_app();
    });

    // View Switching
    const mainView = document.getElementById('main-view');
    const settingsView = document.getElementById('settings-view');

    document.getElementById('settings-btn').addEventListener('click', () => {
        mainView.classList.remove('active');
        settingsView.classList.add('active');
    });

    document.getElementById('back-to-main').addEventListener('click', () => {
        settingsView.classList.remove('active');
        mainView.classList.add('active');
    });

    // Brightness Offset Logic
    const offsetSlider = document.getElementById('brightness-offset');
    const offsetVal = document.getElementById('offset-val');

    // Load existing settings
    try {
        const settings = await api.get_settings();
        if (settings && settings.brightness_offset !== undefined) {
            const offset = settings.brightness_offset;
            offsetSlider.value = offset;
            offsetVal.textContent = offset > 0 ? `+${offset}` : offset;
            // Map -20..20 to 0..100% for CSS
            const percent = ((offset + 20) / 40) * 100;
            offsetSlider.style.setProperty('--val', `${percent}%`);
        }
    } catch (e) { console.error("Error loading settings:", e); }

    offsetSlider.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        offsetVal.textContent = val > 0 ? `+${val}` : val;
        const percent = ((val + 20) / 40) * 100;
        offsetSlider.style.setProperty('--val', `${percent}%`);
        api.set_brightness_offset(val);
    });

    // Fetch and populate info
    try {
        const info = await api.get_info();
        if (info && !info.error) {
            document.getElementById('location-text').textContent = `${info.city}, ${info.country}`;
            document.getElementById('temperature').textContent = `${info.temperature}°C`;
            
            // Format time
            const formatTime = (isoString) => {
                const d = new Date(isoString);
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            };
            
            document.getElementById('sunrise-time').textContent = formatTime(info.sunrise);
            document.getElementById('sunset-time').textContent = formatTime(info.sunset);
            
            // Basic weather icon logic based on WMO code
            const weatherIcon = document.getElementById('weather-icon');
            if (info.weather_code <= 1) weatherIcon.className = 'ph ph-sun';
            else if (info.weather_code <= 3) weatherIcon.className = 'ph ph-cloud-sun';
            else if (info.weather_code <= 49) weatherIcon.className = 'ph ph-cloud';
            else if (info.weather_code <= 69) weatherIcon.className = 'ph ph-cloud-rain';
            else if (info.weather_code <= 79) weatherIcon.className = 'ph ph-cloud-snow';
            else weatherIcon.className = 'ph ph-cloud-lightning';
        }
    } catch (e) {
        console.error("Failed to fetch info:", e);
    }

    // Fetch and render monitors
    try {
        const monitorsContainer = document.getElementById('monitors-container');
        const monitors = await api.get_monitors();
        
        monitorsContainer.innerHTML = ''; // Clear loading
        
        if (monitors.length === 0) {
            monitorsContainer.innerHTML = `
                <div class="loading-monitors">
                    <i class="ph ph-warning-circle"></i>
                    <span>No monitors detected</span>
                </div>
            `;
            return;
        }

        monitors.forEach(monitor => {
            const card = document.createElement('div');
            const modeClass = monitor.auto_adjust ? 'auto-mode' : 'manual-mode';
            card.className = `monitor-card ${modeClass}`;
            
            const iconClass = monitor.name.toLowerCase().includes('generic') || monitor.id > 0 ? 'ph-monitor' : 'ph-laptop';
            const checkedAttr = monitor.auto_adjust ? 'checked' : '';
            
            card.innerHTML = `
                <div class="monitor-header">
                    <div class="monitor-title-wrapper">
                        <i class="ph ${iconClass} monitor-icon"></i>
                        <span class="monitor-name">${monitor.name || `Monitor ${monitor.id + 1}`}</span>
                    </div>
                    <div class="smart-adjust-control">
                        <span>Auto</span>
                        <label class="switch">
                            <input type="checkbox" id="auto-toggle-${monitor.id}" ${checkedAttr}>
                            <span class="slider round"></span>
                        </label>
                    </div>
                </div>
                
                <div class="sliders-container">
                    <div class="slider-group">
                        <div class="slider-labels">
                            <span><i class="ph ph-sun"></i> Brightness</span>
                            <span class="slider-val" id="b-val-${monitor.id}">${monitor.brightness}%</span>
                        </div>
                        <input type="range" id="b-slider-${monitor.id}" class="range-brightness" min="0" max="100" value="${monitor.brightness}" style="--val: ${monitor.brightness}%">
                    </div>

                    <div class="slider-group">
                        <div class="slider-labels">
                            <span><i class="ph ph-circle-half-tilt"></i> Contrast</span>
                            <span class="slider-val" id="c-val-${monitor.id}">${monitor.contrast}%</span>
                        </div>
                        <input type="range" id="c-slider-${monitor.id}" class="range-contrast" min="0" max="100" value="${monitor.contrast}" style="--val: ${monitor.contrast}%">
                    </div>
                </div>
            `;
            
            monitorsContainer.appendChild(card);
            
            // Event listeners
            const mToggle = document.getElementById(`auto-toggle-${monitor.id}`);
            mToggle.addEventListener('change', (e) => {
                const isAuto = e.target.checked;
                api.set_monitor_auto(monitor.key, isAuto);
                if (isAuto) {
                    card.classList.add('auto-mode');
                    card.classList.remove('manual-mode');
                    // Force an immediate recalculation when auto is turned on
                    api.force_auto_adjust();
                } else {
                    card.classList.add('manual-mode');
                    card.classList.remove('auto-mode');
                }
            });
            
            const debouncedBrightness = debounce((id, val) => api.set_brightness(id, val), 100);
            const debouncedContrast = debounce((id, val) => api.set_contrast(id, val), 100);
            
            const bSlider = document.getElementById(`b-slider-${monitor.id}`);
            const bVal = document.getElementById(`b-val-${monitor.id}`);
            bSlider.addEventListener('input', (e) => {
                const val = e.target.value;
                bVal.textContent = `${val}%`;
                e.target.style.setProperty('--val', `${val}%`);
                debouncedBrightness(monitor.id, parseInt(val));
            });
            
            const cSlider = document.getElementById(`c-slider-${monitor.id}`);
            const cVal = document.getElementById(`c-val-${monitor.id}`);
            cSlider.addEventListener('input', (e) => {
                const val = e.target.value;
                cVal.textContent = `${val}%`;
                e.target.style.setProperty('--val', `${val}%`);
                debouncedContrast(monitor.id, parseInt(val));
            });
        });
        
    } catch (e) {
        console.error("Failed to fetch monitors:", e);
    }
}
