import dht
import ds18x20
import esp8266_i2c_lcd as i2c_lcd
import machine
import onewire

import uasyncio as asyncio
import ujson

sensors = dict()


async def read_temperature(pin_number):
    global sensors
    pin = machine.Pin(pin_number)
    sensor = ds18x20.DS18X20(onewire.OneWire(pin))
    roms = sensor.scan()
    rom = roms[0]

    while True:
        sensor.convert_temp()
        await asyncio.sleep_ms(750)
        sensors['ds18x20'] = dict(
            temp=sensor.read_temp(rom)
        )


async def read_dht(pin_number):
    global sensors
    pin = machine.Pin(pin_number)
    sensor = dht.DHT11(pin)

    while True:
        sensor.measure()
        sensors['dht'] = dict(
            rel=sensor.humidity(),
            temp=float(sensor.temperature())
        )
        await asyncio.sleep_ms(2000)


def format_value(value):
    if isinstance(value, float):
        return "{:.2f}".format(value)
    else:
        return str(value)


async def update_display():
    global sensors
    i2c = machine.I2C(
        scl=machine.Pin(5),
        sda=machine.Pin(4),
        freq=400000
    )
    lcd = i2c_lcd.I2cLcd(i2c, 0x3F, 2, 16)

    while True:
        print(sensors)
        texts = []
        for values in sensors.values():
            for sensor, value in values.items():
                if sensor == 'temp':
                    unit = 'C'
                elif sensor == 'rel':
                    unit = '%rel'
                else:
                    unit = ''

                texts.append("{:8}".format(format_value(value) + unit))

        lcd.move_to(0, 0)
        lcd.putstr("".join(texts))
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


def main():
    loop = asyncio.get_event_loop()

    loop.create_task(read_dht(0))
    loop.create_task(read_temperature(2))
    loop.create_task(update_display())
    loop.call_soon(
        asyncio.start_server(
            handle_request,
            '0.0.0.0',
            8080,
            backlog=100
        )
    )
    loop.run_forever()


if __name__ == '__main__':
    main()
