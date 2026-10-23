"""Immutable built-in choices and locally saved copies of custom EQ bands."""
import json
import uuid
from types import MappingProxyType

BUILTIN_PRESETS=(('Out loud',0),('Vocal',1),('Intimate',2),('Bass boost',3))
# Display previews, not measured or firmware-readable preset coefficients.
PREVIEW_CURVES=MappingProxyType({0:(0,0,0,0,0),1:(-4,0,1,2,1),2:(0,-2,-4,0,0),3:(3,4,0,-4,-4)})


def preview_bands(code):
    return [round(value*127/12) for value in PREVIEW_CURVES.get(code,(0,)*5)]


def valid_bands(bands):
    return isinstance(bands,list) and len(bands)==5 and all(type(v) is int and -128<=v<=127 for v in bands)


def load_profiles(settings):
    try:
        profiles=json.loads(str(settings.value('eq/profiles','{}')))
    except (ValueError,TypeError):return {}
    if not isinstance(profiles,dict):return {}
    return {key:profile for key,profile in profiles.items()
            if isinstance(profile,dict) and isinstance(profile.get('name'),str)
            and profile['name'].strip() and valid_bands(profile.get('bands'))}


def save_profile(settings,name,bands):
    name=name.strip()
    if not name or len(name)>64:raise ValueError('Choose a profile name between 1 and 64 characters.')
    if not valid_bands(bands):raise ValueError('Five valid equalizer levels are required.')
    profiles=load_profiles(settings)
    reserved={label.casefold() for label,_ in BUILTIN_PRESETS}|{'custom','custom draft'}
    if name.casefold() in reserved:raise ValueError('Choose a new name. Built-in presets are locked.')
    if any(p['name'].casefold()==name.casefold() for p in profiles.values()):
        raise ValueError('That name is already saved. Choose a new name to keep the original profile.')
    key='profile:'+uuid.uuid4().hex
    profiles[key]={'name':name,'bands':list(bands)}
    settings.setValue('eq/profiles',json.dumps(profiles))
    settings.sync()
    if settings.status()!=settings.Status.NoError:raise ValueError('Could not save the profile on this computer.')
    return key
