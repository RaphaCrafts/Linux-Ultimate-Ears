from pathlib import Path
import pytest
from speakerstudio.desktop import register_appimage, quote_exec


def test_launcher_uses_persistent_appimage_and_survives_move(tmp_path):
    image=tmp_path/'Speaker studio % blue.AppImage';image.write_bytes(b'test')
    icon=tmp_path/'icon.png';icon.write_bytes(b'icon')
    data=tmp_path/'xdg'
    env={'APPIMAGE':str(image),'XDG_DATA_HOME':str(data)}
    launcher=register_appimage(icon,env)
    content=launcher.read_text()
    assert f'Exec=/bin/sh "{data}/speaker-studio/launch"' in content
    assert str(image) in (data/'speaker-studio/launch').read_text()
    assert 'StartupWMClass=speaker-studio' in content
    assert (data/'icons/hicolor/512x512/apps/speaker-studio.png').read_bytes()==b'icon'
    moved=tmp_path/'moved.AppImage';image.rename(moved);env['APPIMAGE']=str(moved)
    register_appimage(icon,env)
    script=(data/'speaker-studio/launch').read_text()
    assert str(moved) in script and str(image) not in script


def test_source_runs_do_not_install_and_unrelated_launcher_is_preserved(tmp_path):
    assert register_appimage(tmp_path/'absent',{}) is None
    image=tmp_path/'app';image.write_bytes(b'test')
    data=tmp_path/'xdg';apps=data/'applications';apps.mkdir(parents=True)
    launcher=apps/'speaker-studio.desktop';launcher.write_text('Unrelated user shortcut')
    with pytest.raises(ValueError):
        register_appimage(tmp_path/'absent',{'APPIMAGE':str(image),'XDG_DATA_HOME':str(data)})
    assert launcher.read_text()=='Unrelated user shortcut'


def test_exec_argument_escaping():
    assert quote_exec('/a b/100%.AppImage')=='"/a b/100%%.AppImage"'
    with pytest.raises(ValueError):quote_exec('/a\nb')
    with pytest.raises(ValueError):quote_exec('/a\rb')
