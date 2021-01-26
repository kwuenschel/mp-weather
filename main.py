import dht
import ds18x20
import framebuf
import machine
import onewire

import uasyncio as asyncio
import ujson

sensors = dict()


async def read_ds18x20(name, pin_number):
    global sensors
    pin = machine.Pin(pin_number)
    sensor = ds18x20.DS18X20(onewire.OneWire(pin))
    roms = sensor.scan()
    rom = roms[0]

    while True:
        sensor.convert_temp()
        await asyncio.sleep_ms(750)
        sensors[name] = dict(
            temp=sensor.read_temp(rom)
        )


async def read_dht(name, pin_number):
    global sensors
    pin = machine.Pin(pin_number)
    sensor = dht.DHT11(pin)

    while True:
        sensor.measure()
        sensors[name] = dict(
            rel=sensor.humidity(),
            temp=float(sensor.temperature())
        )
        await asyncio.sleep_ms(2000)


async def update_display(display, sensor_config):
    global sensors

    while True:
        print(sensors)
        texts = []
        for name, config in sensor_config:
            values = sensors.get(name)
            if values:
                texts.append(config['format'].format(**values))

        text = "".join(texts)
        display.show_text(text)
        await asyncio.sleep_ms(2000)


async def handle_request(reader, writer):
    global sensors
    request = yield from reader.read()
    method, url, *_ = request.decode('utf-8').split(' ')
    if method == 'GET':
        if url == '/':
            yield from writer.awrite(
                'HTTP/1.0 200 OK\n'
                'Content-Type: application/json\r\n\r\n'
            )
            yield from writer.awrite(
                ujson.dumps(
                    sensors
                )
            )

    yield from writer.aclose()


def read_config():
    with open('config.json') as f:
        return ujson.loads(f.read())


def main():
    config = read_config()

    loop = asyncio.get_event_loop()

    for name, sensor_config in config['sensors'].items():
        if sensor_config['type'] == 'dht11':
            loop.create_task(read_dht(name, sensor_config['pin']))
        elif sensor_config['type'] == 'ds18x20':
            loop.create_task(read_ds18x20(name, sensor_config['pin']))
        else:
            print(
                'Configuration error: Unknown sensor {}'.format(
                    sensor_config['type']
                )
            )

    if 'display' in config:
        display_config = config['display']
        display_type = display_config.pop('type', 'i2lcd')
        if display_type == 'i2lcd':
            display = I2CLCD(
                scl=display_config['pin']['scl'],
                sda=display_config['pin']['sda'],
                address=display_config['address'],
                width=display_config['dimensions']['width'],
                height=display_config['dimensions']['height'],
            )
        elif display_type == 'ssd1306':
            display = SSD1306(
                scl=display_config['pin']['scl'],
                sda=display_config['pin']['sda'],
                width=display_config['dimensions']['width'],
                height=display_config['dimensions']['height'],
            )
        else:
            raise ValueError("Unknown display type {}".format(display_type))

        loop.create_task(
            update_display(
                display,
                config['sensors'].items()
            )
        )

    if 'httpd' in config:
        loop.call_soon(
            asyncio.start_server(
                handle_request,
                config['httpd'].get('listen_address', '0.0.0.0'),
                config['httpd'].get('port', 8080),
                backlog=100,
            )
        )
    loop.run_forever()


class SSD1306:
    def __init__(self, scl, sda, width, height):
        import ssd1306
        self.i2c = machine.I2C(
            scl=machine.Pin(scl),
            sda=machine.Pin(sda),
            freq=100000,
        )
        self.display = ssd1306.SSD1306_I2C(
            width,
            height,
            self.i2c,
        )
        self.chars_per_line = width // 8

    def show_text(self, text):
        self.display.fill(0)
        line_count = len(text) // self.chars_per_line + 1
        for line in range(line_count):
            self.display.text(text[line*self.chars_per_line:(line+1)*self.chars_per_line], 0, line * 8)

        self.display.show()


class I2CLCD:
    def __init__(self, scl, sda, address, width, height):
        import esp8266_i2c_lcd as i2c_lcd
        self.i2c = machine.I2C(
            scl=machine.Pin(scl),
            sda=machine.Pin(sda),
            freq=400000,
        )
        self.lcd = i2c_lcd.I2cLcd(
            self.i2c,
            address,
            height,
            width,
        )

    def show_text(text):
        self.lcd.move_to(0, 0)
        self.lcd.putstr(text)


if __name__ == '__main__':
    main()
