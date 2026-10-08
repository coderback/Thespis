using System.IO;
using UnityEditor.AssetImporters;
using UnityEngine;

namespace Thespis.Editor
{
    /// <summary>A game.toml imported as a TextAsset, so a ThespisSettings asset can point at it and a build ships it.</summary>
    [ScriptedImporter(1, "toml")]
    public sealed class TomlImporter : ScriptedImporter
    {
        public override void OnImportAsset(AssetImportContext ctx)
        {
            var text = new TextAsset(File.ReadAllText(ctx.assetPath));
            ctx.AddObjectToAsset("text", text);
            ctx.SetMainObject(text);
        }
    }
}
