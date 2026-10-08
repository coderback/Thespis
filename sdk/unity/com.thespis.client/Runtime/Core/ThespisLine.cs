#nullable enable
using System;
using System.Threading.Tasks;
using Thespis.Api;

namespace Thespis
{
    /// <summary>
    /// A line an NPC speaks, or the narrator tells. It may arrive provisional: the game's own template line, ready to
    /// show at once, which the model's line replaces when it settles. The client follows a provisional line and
    /// updates this same object, so a line the game keeps hold of is always the latest; <see cref="Settled"/> fires
    /// when it is final or withdrawn.
    /// </summary>
    public sealed class ThespisLine : LineOut
    {
        /// <summary>Final (show the new text) or withdrawn (take it down).</summary>
        public event Action<ThespisLine>? Settled;

        /// <summary>Why it couldn't be followed to the end, if it couldn't; its text is still safe to show.</summary>
        public string SettleError { get; internal set; } = "";

        internal TaskCompletionSource<bool>? Following;

        public bool IsProvisional => Status == "provisional";
        public bool IsFinal => Status == "final";
        /// <summary>Don't show it: the model's line failed every check and there was no template line.</summary>
        public bool IsWithdrawn => Status == "withdrawn";
        public bool IsSettled => !IsProvisional;
        /// <summary>The NPC chose to say nothing. That differs from an empty line, so <c>Text</c> is null.</summary>
        public bool IsSilent => Text == null;

        /// <summary>The words, or <paramref name="otherwise"/> when the NPC is silent or the line was withdrawn.</summary>
        public string Words(string otherwise = "") => Text == null || IsWithdrawn ? otherwise : Text;

        internal void RaiseSettled() => Settled?.Invoke(this);
    }
}
