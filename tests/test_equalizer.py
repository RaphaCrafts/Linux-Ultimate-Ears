import json
import pytest
from PySide6.QtCore import QSettings
from speakerstudio.equalizer import load_profiles, save_profile


def test_saved_profiles_never_overwrite_builtins_or_existing_names(tmp_path):
    settings=QSettings(str(tmp_path/'profiles.ini'),QSettings.IniFormat)
    for name in ('Out loud','VOCAL',' Intimate ','Bass boost','Custom'):
        with pytest.raises(ValueError,match='locked'):save_profile(settings,name,[0]*5)
    bands=[1,2,3,4,5]
    key=save_profile(settings,'Evening',bands)
    bands[0]=99
    assert load_profiles(settings)[key]['bands']==[1,2,3,4,5]
    with pytest.raises(ValueError,match='already saved'):save_profile(settings,'evening',[0]*5)
    assert len(load_profiles(settings))==1
    for invalid in ([1],['1']*5,[True]*5,[128]*5):
        with pytest.raises(ValueError):save_profile(settings,'Other',invalid)


def test_malformed_saved_profile_data_is_ignored(tmp_path):
    settings=QSettings(str(tmp_path/'profiles.ini'),QSettings.IniFormat)
    for value in ('garbled','[]',json.dumps({'x':{'name':'Broken','bands':[128]*5}})):
        settings.setValue('eq/profiles',value)
        assert load_profiles(settings)=={}
