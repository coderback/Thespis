## A line an NPC speaks, or the narrator tells. It may arrive provisional: the game's own template line, ready to
## show at once, which the model's line replaces when it settles. The client follows a provisional line and updates
## this same object, so a line the game keeps hold of is always the latest; `settled` fires when it is final or
## withdrawn.
class_name ThespisLine
extends ThespisApi.LineOut

signal settled(line: ThespisLine)  ## final (show the new text) or withdrawn (take it down)
signal _followed  ## the client stopped following it, settled or not

var settle_error := ""  ## why it couldn't be followed to the end, if it couldn't; its text is still safe to show


func is_provisional() -> bool:
	return status == "provisional"


func is_final() -> bool:
	return status == "final"


## Don't show it: the model's line failed every check and there was no template line to fall back to.
func is_withdrawn() -> bool:
	return status == "withdrawn"


func is_settled() -> bool:
	return not is_provisional()


## The NPC chose to say nothing. That differs from an empty line, so `text` is null rather than "".
func is_silent() -> bool:
	return text == null


## The words, or `otherwise` when the NPC is silent or the line was withdrawn.
func words(otherwise := "") -> String:
	return otherwise if text == null or is_withdrawn() else str(text)
