"""Read-only installed-bundle check, kept out of the everyday user interface."""
import asyncio
import json
from dataclasses import asdict
from .backend import Controller
from .bluez import BlueZ
from .models import Speaker


def check_speaker(address):
    async def run():
        controller=Controller()
        controller.loop=asyncio.get_running_loop()
        controller.bluez=BlueZ()
        try:
            await controller.bluez.start()
            rows,_=await controller.bluez.devices()
            row=next((r for r in rows if r['address'].upper()==address.upper()),None)
            if not row:
                raise RuntimeError('Paired speaker not found. Pair it in Bluetooth settings first.')
            address_key=row['address']
            controller.speakers[address_key]=Speaker(address_key,row['path'],row['name'],paired=row['paired'])
            await controller._connect(address_key)
            state=asdict(controller.speakers[address_key])
            fields=('model','identity','firmware','battery','volume','eq','bands','broadcast','colour','colour_code')
            print(json.dumps({k:state[k] for k in fields},indent=2),flush=True)
            return 0
        except Exception as error:
            print('Speaker check failed: '+str(error),flush=True)
            return 1
        finally:
            for session in controller.sessions.values():session.close()
            await controller.bluez.close()
    return asyncio.run(run())
