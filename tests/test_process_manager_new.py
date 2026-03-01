import pytest
from unittest.mock import patch, MagicMock
from src.process_manager import fetch_sessions_for_host, validate_ssh_target, build_terminal_command
from src.app import pty_restart

def test_fetch_sessions_for_host_local():
    host = {'type': 'local', 'target': None, 'dir': None}
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='  1. Local (test) [uuid]', stderr='')
        
        result = fetch_sessions_for_host(host, '/tmp/.ssh')
        assert result['output'] == '  1. Local (test) [uuid]'
        assert mock_run.called

def test_fetch_sessions_for_host_ssh():
    host = {'type': 'ssh', 'target': 'user@remote', 'dir': '~/myproject'}
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='  1. Remote (test) [uuid]', stderr='')
        
        result = fetch_sessions_for_host(host, '/tmp/.ssh')
        assert result['output'] == '  1. Remote (test) [uuid]'
        
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert 'ssh' in cmd
        assert 'user@remote' in cmd
        remote_bash_cmd = cmd[-1]
        assert 'bash -l -c' in remote_bash_cmd
        assert '~/myproject' in remote_bash_cmd or 'myproject' in remote_bash_cmd
        assert 'gemini --list-sessions' in remote_bash_cmd

def test_validate_ssh_target_invalid():
    assert not validate_ssh_target("user@host; rm -rf /")
    assert validate_ssh_target("user@192.168.1.100")
    assert validate_ssh_target("user@host.com:2222")

@patch('pty.fork')
@patch('os.execvp')
@patch('os._exit')
def test_pty_restart_local_cmd(mock_exit, mock_execvp, mock_fork):
    # Simulate being the child process
    mock_fork.return_value = (0, 1) # child_pid=0, fd=1
    
    data = {
        'tab_id': 'test_tab',
        'resume': True
    }
    
    # Needs to run in app context to access session
    from src.app import app
    with app.test_request_context('/'):
        pty_restart(data)
        
    mock_execvp.assert_called_once()
    cmd = mock_execvp.call_args[0][1]
    assert cmd[0] == '/bin/sh'
    assert 'gemini -r' in cmd[2]
    assert 'WARNING: Persistence volume not found' in cmd[2]

@patch('pty.fork')
@patch('os.execvp')
@patch('os._exit')
def test_pty_restart_ssh_cmd(mock_exit, mock_execvp, mock_fork):
    # Simulate being the child process
    mock_fork.return_value = (0, 1) # child_pid=0, fd=1
    
    data = {
        'tab_id': 'test_tab',
        'resume': True,
        'ssh_target': 'user@remote.com',
        'ssh_dir': '~/dev/project'
    }
    
    from src.app import app
    with app.test_request_context('/'):
        pty_restart(data)
        
    mock_execvp.assert_called_once()
    cmd = mock_execvp.call_args[0][1]
    assert cmd[0] == 'ssh'
    assert 'user@remote.com' in cmd
    
    remote_cmd = cmd[-1]
    assert 'bash -l -c' in remote_cmd
    assert 'gemini -r' in remote_cmd
    assert 'cd ~' in remote_cmd
    assert 'dev/project' in remote_cmd
