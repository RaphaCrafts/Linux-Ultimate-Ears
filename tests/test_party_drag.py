import asyncio
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt, QMimeData, QPoint, QPointF
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QPushButton
from speakerstudio.backend import Controller
from speakerstudio.ui import Window
from speakerstudio.party_visual import SPEAKER_MIME, SpeakerDragCard
from speakerstudio.protocol import Message
from speakerstudio.models import Speaker


def mime(host,receiver):
    data=QMimeData();data.setData(SPEAKER_MIME,json.dumps({'host':host,'receiver':receiver}).encode());return data


def window(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path))
    app=QApplication.instance() or QApplication([])
    w=Window(Controller(),demo=True);app.processEvents();w.navigate('party')
    return app,w


def test_receiving_speaker_is_never_selected_as_existing_group_host(tmp_path,monkeypatch):
    app,w=window(tmp_path,monkeypatch)
    host=w.devices['demo-0'];receiver=w.devices['demo-1']
    w.devices={receiver['address']:receiver,host['address']:host}
    w.group_host=receiver['address'];w.render_party()
    assert w.group_host==host['address']
    assert w.host_select.findData(receiver['address'])==-1
    assert '1 group members' in w.party_info.text()
    w.close()


def test_drag_and_button_join_share_confirmation_path(tmp_path,monkeypatch):
    app,w=window(tmp_path,monkeypatch)
    host=w.devices[w.group_host];receiver=w.devices['demo-1']
    host.update(members=[],broadcast=0)
    w.render_party()
    assert w.available_grid.itemAt(0).widget().__class__ is SpeakerDragCard
    calls=[];w.demo=False
    monkeypatch.setattr(w.controller,'submit',lambda *args:calls.append(args))
    data=mime(host['address'],receiver['address'])
    enter=QDragEnterEvent(QPoint(15,15),Qt.MoveAction,data,Qt.LeftButton,Qt.NoModifier)
    app.sendEvent(w.play_area,enter);assert enter.isAccepted()
    drop=QDropEvent(QPointF(15,15),Qt.MoveAction,data,Qt.LeftButton,Qt.NoModifier)
    app.sendEvent(w.play_area,drop)
    assert drop.isAccepted() and calls==[('group_add',host['address'],receiver['address'])]
    assert host['members']==[], 'A drop is a request, not confirmed playback'
    button=next(b for b in w.available_grid.itemAt(0).widget().findChildren(QPushButton) if b.text()=='Add to group')
    button.click()
    assert calls[-1]==calls[0] and len(calls)==2
    host.update(busy=True,operation='group_add',group_target=receiver['address'])
    w.render_party()
    assert 'Waiting for' in w.play_hint.text()
    assert w.party_grid.count()==2 and w.available_grid.count()==1
    assert not w.play_area.receiver_from(data)
    host.update(busy=False,operation='',group_target='',error='Could not join this speaker.')
    w.render_party()
    assert w.party_error.text()=='Could not join this speaker.' and not w.party_error.isHidden()
    stale=mime('another-host',receiver['address'])
    assert w.play_area.receiver_from(stale) is None
    assert w.play_area.receiver_from(mime(host['address'],'unknown')) is None
    w.close()


def test_confirmed_inventory_completes_join_without_add_event():
    async def scenario():
        c=Controller();host='00:11:22:33:44:55';receiver='00:11:22:33:44:66'
        c.speakers[host]=Speaker(host,'','Host',connected=True,broadcast=3)
        future=asyncio.get_running_loop().create_future()
        c.group_waiters[(host,0x418,receiver)]=future
        record=bytes.fromhex(receiver.replace(':',''))+b'\x50\x03\x00\x00'
        c._notification(host,Message(0x416,b'\x01'+record))
        assert not future.done(), 'Nearby does not mean joined'
        record=bytes.fromhex(receiver.replace(':',''))+b'\x50\x08\x00\x00'
        c._notification(host,Message(0x416,b'\x01'+record))
        assert await future is True and c.speakers[host].members==[receiver]
        # A repeated request for a confirmed receiver needs no receiver socket.
        await c._group_add(host,receiver)
    asyncio.run(scenario())


def test_join_reads_current_broadcast_before_reconfiguring():
    async def scenario():
        c=Controller();c.loop=asyncio.get_running_loop()
        host='00:11:22:33:44:55';receiver='00:11:22:33:44:66'
        c.speakers={a:Speaker(a,'',a,connected=True,features={'group':True}) for a in (host,receiver)}
        class Session:
            commands=[]
            async def request(self,command,response=0,payload=b''):
                self.commands.append(command)
                if command==0x414:return b'\x03\x50'
                if command==0x417:c._notification(host,Message(0x418,bytes.fromhex(receiver.replace(':',''))+b'\0'))
                return b''
        session=Session();c.sessions[host]=session
        await c._group_add(host,receiver)
        assert session.commands==[0x414,0x417], 'Do not restart a group that is already broadcasting'
        assert c.speakers[host].audio_mode==0x50
    asyncio.run(scenario())


def test_background_update_retains_drag_source_and_rejects_newly_busy_host(tmp_path,monkeypatch):
    app,w=window(tmp_path,monkeypatch)
    host=w.devices[w.group_host];host.update(members=[],broadcast=0)
    w.render_party();card=w.available_grid.itemAt(0).widget()
    w.party_drag_changed(True)
    host.update(busy=True,operation='group_add',group_target='demo-1')
    w.render_party()
    assert w.available_grid.itemAt(0).widget() is card
    assert w.play_area.receiver_from(mime(host['address'],'demo-1')) is None
    w.party_drag_changed(False);app.processEvents()
    assert w.party_grid.count()==2 and 'Waiting for' in w.play_hint.text()
    w.close()
