## The period faces the design canvas sets the paper in, shipped with the game (assets/fonts, each with its licence):
## Old Standard TT for the print, IM Fell English SC for names and titles, Special Elite for typewritten slips,
## Cedarville Cursive for Anton's hand. A face missing a letter (the č and ě of Czech names, in the older faces)
## falls back to Old Standard, which has them.
class_name Fonts
extends RefCounted

static var serif: FontFile
static var italic: FontFile
static var bold: FontFile
static var caps: FontFile
static var type: FontFile
static var hand: FontFile


static func _static_init() -> void:
	serif = load("res://assets/fonts/oldstandardtt/OldStandard-Regular.ttf")
	italic = load("res://assets/fonts/oldstandardtt/OldStandard-Italic.ttf")
	bold = load("res://assets/fonts/oldstandardtt/OldStandard-Bold.ttf")
	caps = load("res://assets/fonts/imfellenglishsc/IMFeENsc28P.ttf")
	type = load("res://assets/fonts/specialelite/SpecialElite-Regular.ttf")
	hand = load("res://assets/fonts/cedarvillecursive/Cedarville-Cursive.ttf")
	caps.fallbacks = [serif]
	type.fallbacks = [serif]
	hand.fallbacks = [italic]
