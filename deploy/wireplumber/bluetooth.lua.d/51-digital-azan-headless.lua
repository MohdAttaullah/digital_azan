-- The Digital Azan audio session starts through systemd user lingering, before
-- any interactive logind session exists. Keep BlueZ audio available in that
-- headless session so the trusted speaker can reconnect after boot.
bluez_monitor.properties["with-logind"] = false
bluez_monitor.properties["bluez5.codecs"] = "[ sbc ]"
