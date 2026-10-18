import asyncio
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import asdict
from PySide6.QtWidgets import QApplication
from speakerstudio.firmware import FirmwareDialog, OFFICIAL_APP_URL
from speakerstudio.models import Speaker
from speakerstudio.backend import Controller
from speakerstudio.protocol import ProtocolError


def test_version_read_only_queries_firmware_and_preserves_group():
    async def scenario():
        c=Controller();s=Speaker('test','','Speaker',connected=True,broadcast=3,members=['receiver'])
        c.speakers={'test':s}
        class Session:
            commands=[]
            async def request(self,command,response=0,payload=b''):
                self.commands.append((command,response,payload));return b'\x01\x06\x2d'
        session=Session();c.sessions={'test':session}
        await c._firmware('test')
        assert s.firmware=='1.6.45' and s.broadcast==3 and s.members==['receiver']
        assert session.commands==[(3,4,b'')]
    asyncio.run(scenario())


def test_firmware_dialog_distinguishes_installed_cached_and_unknown():
    app=QApplication.instance() or QApplication([])
    class Controller:
        calls=[]
        def submit(self,*args):self.calls.append(args)
    controller=Controller()
    s=asdict(Speaker('test','','PURPLE 3',connected=True,firmware='1.6.45'))
    d=FirmwareDialog(s,controller)
    assert d.version.text()=='Installed version: 1.6.45'
    d.read.click();assert controller.calls==[('firmware','test')]
    d.release.click();assert controller.calls[-1]==('disconnect','test')
    s.update(connected=False);d.update_speaker(s)
    assert d.version.text()=='Last read version: 1.6.45'
    assert not d.read.isEnabled() and not d.release.isEnabled()
    s.update(firmware='',connected=True,busy=True);d.update_speaker(s)
    assert not d.read.isEnabled()
    s.update(busy=False,error='Speaker did not reply');d.update_speaker(s)
    assert d.error.text()=='Speaker did not reply'
    demo=FirmwareDialog(s,controller,demo=True)
    assert not demo.read.isEnabled() and 'demo' in demo.version.text()
    assert OFFICIAL_APP_URL.startswith('https://www.ultimateears.com/')
    demo.close();d.close()
