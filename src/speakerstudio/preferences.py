"""Last verified speaker appearance, separate from manual finish overrides."""
from PySide6.QtCore import QSettings


def device_settings():
    return QSettings('RaphaCrafts','SpeakerStudio')


def remembered_model(address):
    return str(device_settings().value('devices/'+address+'/model',''))


def restore_appearance(device, settings):
    """Return a copy; do not mutate the controller's emitted snapshot."""
    d=dict(device)
    prefix='devices/'+d['address']+'/'
    before={key:settings.value(prefix+key,None) for key in ('model','colour_code','colour')}
    if d.get('model'):
        settings.setValue(prefix+'model',d['model'])
    else:
        d['model']=str(settings.value(prefix+'model',''))
    if d.get('colour_code') is not None:
        settings.setValue(prefix+'colour_code',str(d['colour_code']))
        settings.setValue(prefix+'colour',d.get('colour',''))
    elif d.get('colour'):
        settings.setValue(prefix+'colour',d['colour'])
    else:
        d['colour']=str(settings.value(prefix+'colour',''))
        d['remembered_colour']=bool(d['colour'])
    if any(settings.value(prefix+key,None)!=value for key,value in before.items()):settings.sync()
    return d


def remembered_models():
    settings=device_settings()
    settings.beginGroup('devices')
    return {address:str(settings.value(address+'/model','')) for address in settings.childGroups()
            if settings.value(address+'/model','')}
