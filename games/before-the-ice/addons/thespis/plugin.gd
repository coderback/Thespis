## The Thespis editor plugin: enabling it adds the `Thespis` autoload (a ThespisClient) and its Project Settings.
@tool
extends EditorPlugin

const AUTOLOAD := "Thespis"


func _enable_plugin() -> void:
	add_autoload_singleton(AUTOLOAD, "res://addons/thespis/thespis.gd")


func _disable_plugin() -> void:
	remove_autoload_singleton(AUTOLOAD)


func _enter_tree() -> void:
	ThespisClient.register_settings()  # shown in Project Settings; saved only when one is changed
