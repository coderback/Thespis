## The Thespis runtime as a sidecar: started beside the game, on this machine only, and stopped with it.
##
## It runs `thespis serve --port 0`, reads the URL it prints, and keeps a random token so no other program on the
## machine can use it. The runtime stops when the game does: this node kills it on the way out, and `--parent` makes
## the runtime watch the game's process in case the game is killed first. It's offline unless told otherwise, so a
## shipped game's minds need nothing but the player's machine (docs/serve.md).
class_name ThespisSidecar
extends Node

const URL_LINE := "THESPIS_URL="
const LOG_KEEP := 8192  ## bytes of the runtime's own log kept, for saying why it failed

## How to run the runtime. Empty: the packaged runtime beside the game's executable (thespis/thespis.exe, from
## tools/package.py) if it's there, else `python -m thespis`, for development.
var command := PackedStringArray()
var model := ""  ## a local model to speak through (`--local`): auto, or a model id such as gemma4-e4b
var online := false  ## may the runtime reach the network (a cloud model)? A shipped offline game leaves this off
var db := "user://thespis/sessions.sqlite"  ## where its sessions are kept between runs
var start_timeout := 120.0  ## seconds to wait for it, a local model's first load included

var url := ""  ## where it listens, once started
var token := ""  ## what every call must present
var pid := -1
var log_tail := ""  ## the tail of the runtime's own log

var _out: FileAccess
var _err: FileAccess
var _buffer := ""


## The runtime the game ships with, or Python in development.
static func default_command() -> PackedStringArray:
	var exe := "thespis.exe" if OS.get_name() == "Windows" else "thespis"
	var here := OS.get_executable_path().get_base_dir()
	for dir in [here.path_join("thespis"), here]:
		if FileAccess.file_exists(dir.path_join(exe)):
			return PackedStringArray([dir.path_join(exe)])
	return PackedStringArray(["python", "-m", "thespis"])


## Start the runtime and wait until it says where it listens. ok, or why not.
func start() -> ThespisResult:
	if is_running():
		return ThespisResult.success(url)
	var cmd := command if not command.is_empty() else default_command()
	var path := ProjectSettings.globalize_path(db)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var args := cmd.slice(1)
	args.append_array(["serve", "--port", "0", "--parent", str(OS.get_process_id()), "--db", path])
	if not model.is_empty():
		args.append_array(["--local", model])
	if online:
		args.append("--online")
	token = Crypto.new().generate_random_bytes(18).hex_encode()
	# The token reaches the runtime through its environment, never its command line, where other programs can read it.
	var had: Variant = OS.get_environment("THESPIS_TOKEN") if OS.has_environment("THESPIS_TOKEN") else null
	OS.set_environment("THESPIS_TOKEN", token)
	var p := OS.execute_with_pipe(cmd[0], args, false)
	if had == null:
		OS.unset_environment("THESPIS_TOKEN")
	else:
		OS.set_environment("THESPIS_TOKEN", had)
	if p.is_empty():
		return ThespisResult.failure("not_started", "couldn't run %s" % " ".join(cmd))
	pid = p["pid"]
	_out = p["stdio"]
	_err = p["stderr"]
	var deadline := Time.get_ticks_msec() + int(start_timeout * 1000)
	while url.is_empty():
		_drain()
		if not OS.is_process_running(pid):
			pid = -1
			return ThespisResult.failure("exited", "the runtime stopped: %s" % log_tail.strip_edges().right(600))
		if Time.get_ticks_msec() > deadline:
			stop()
			return ThespisResult.failure("timeout", "the runtime didn't start in %ss: %s" % [start_timeout,
					log_tail.strip_edges().right(600)])
		await get_tree().create_timer(0.05).timeout
	set_process(true)
	return ThespisResult.success(url)


func is_running() -> bool:
	return pid > 0 and OS.is_process_running(pid)


func stop() -> void:
	set_process(false)
	if is_running():
		OS.kill(pid)
	pid = -1
	url = ""


func _ready() -> void:
	set_process(false)


## Keep reading its output while it runs: a pipe nobody reads fills up, and then the runtime stalls on a log line.
func _process(_delta: float) -> void:
	_drain()


func _exit_tree() -> void:
	stop()


func _drain() -> void:
	if _out:
		var got := _out.get_buffer(4096)
		if not got.is_empty():
			_buffer += got.get_string_from_utf8()
			while "\n" in _buffer:
				var line := _buffer.get_slice("\n", 0).strip_edges()
				_buffer = _buffer.substr(_buffer.find("\n") + 1)
				if line.begins_with(URL_LINE) and url.is_empty():
					url = line.substr(URL_LINE.length())
	if _err:
		var said := _err.get_buffer(65536)
		if not said.is_empty():
			log_tail = (log_tail + said.get_string_from_utf8()).right(LOG_KEEP)
