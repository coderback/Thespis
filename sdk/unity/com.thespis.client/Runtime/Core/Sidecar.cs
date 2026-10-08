#nullable enable
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;

namespace Thespis
{
    /// <summary>
    /// The Thespis runtime as a sidecar: started beside the game, on this machine only, and stopped with it.
    ///
    /// It runs <c>thespis serve --port 0</c>, reads the URL it prints, and gives it a random token through its
    /// environment, so no other program on the machine can use it. The runtime stops when the game does: this kills
    /// it on the way out, and <c>--parent</c> makes the runtime watch the game's process in case the game is killed
    /// first. It's offline unless told otherwise, so a shipped game's minds need nothing but the player's machine.
    /// </summary>
    public sealed class Sidecar : IDisposable
    {
        private const string UrlLine = "THESPIS_URL=";
        private const int LogKeep = 32768;  // enough for a stack dump (kill -USR1) of every thread

        /// <summary>How to run the runtime: the executable, then its arguments.</summary>
        public IReadOnlyList<string> Command { get; set; } = new[] { "python", "-m", "thespis" };
        /// <summary>A local model to speak through (--local): auto, or an id such as gemma4-e4b.</summary>
        public string Model { get; set; } = "";
        /// <summary>May the runtime reach the network (a cloud model)? A shipped offline game leaves this off.</summary>
        public bool Online { get; set; }
        /// <summary>The SQLite file its sessions are kept in between runs; empty, the runtime's own cache folder.</summary>
        public string Sessions { get; set; } = "";
        /// <summary>How long to wait for it, a local model's first load included.</summary>
        public TimeSpan StartTimeout { get; set; } = TimeSpan.FromSeconds(120);

        public string Url { get; private set; } = "";
        public string Token { get; private set; } = "";
        public int Pid => _process != null && !_process.HasExited ? _process.Id : -1;
        public bool IsRunning => _process != null && !_process.HasExited;

        /// <summary>The tail of the runtime's own log, for saying why it failed.</summary>
        public string Log
        {
            get { lock (_log) return _log.ToString(); }
        }

        private Process? _process;
        private readonly StringBuilder _log = new StringBuilder();

        /// <summary>Start the runtime and wait until it says where it listens.</summary>
        public async Task<Result<string>> StartAsync()
        {
            if (IsRunning)
                return Result<string>.Success(Url);
            var args = Command.Skip(1).Concat(new[] { "serve", "--port", "0", "--parent",
                Process.GetCurrentProcess().Id.ToString() }).ToList();
            if (Sessions.Length > 0)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(Sessions))!);
                args.AddRange(new[] { "--db", Sessions });
            }
            if (Model.Length > 0)
                args.AddRange(new[] { "--local", Model });
            if (Online)
                args.Add("--online");
            Token = NewToken();
            var info = new ProcessStartInfo(Command[0], string.Join(" ", args.Select(Quote)))
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            // The token reaches the runtime through its environment, never its command line, which others can read.
            info.Environment["THESPIS_TOKEN"] = Token;
            var found = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
            var process = new Process { StartInfo = info, EnableRaisingEvents = true };
            // Both pipes are read to the end: a pipe nobody reads fills up, and then the runtime stalls on a log line.
            process.OutputDataReceived += (_, e) =>
            {
                if (e.Data != null && e.Data.StartsWith(UrlLine, StringComparison.Ordinal))
                    found.TrySetResult(e.Data.Substring(UrlLine.Length).Trim());
            };
            process.ErrorDataReceived += (_, e) =>
            {
                if (e.Data == null)
                    return;
                lock (_log)
                {
                    _log.Append(e.Data).Append('\n');
                    if (_log.Length > LogKeep)
                        _log.Remove(0, _log.Length - LogKeep);
                }
            };
            process.Exited += (_, _) => found.TrySetResult("");
            try
            {
                process.Start();
            }
            catch (Exception e)
            {
                return Result<string>.Failure("not_started", $"couldn't run {string.Join(" ", Command)}: {e.Message}");
            }
            _process = process;
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            var first = await Task.WhenAny(found.Task, Task.Delay(StartTimeout));
            if (first != found.Task)
            {
                Stop();
                return Result<string>.Failure("timeout", $"the runtime didn't start in {StartTimeout.TotalSeconds}s: {Tail()}");
            }
            Url = found.Task.Result;
            if (Url.Length == 0)
            {
                Stop();
                return Result<string>.Failure("exited", $"the runtime stopped: {Tail()}");
            }
            return Result<string>.Success(Url);
        }

        public void Stop()
        {
            var process = _process;
            _process = null;
            Url = "";
            if (process == null)
                return;
            try
            {
                if (!process.HasExited)
                    process.Kill();
                process.WaitForExit(5000);
            }
            catch (InvalidOperationException)
            {
                // it had already gone
            }
            process.Dispose();
        }

        public void Dispose() => Stop();

        private string Tail()
        {
            var log = Log.Trim();
            return log.Length > 600 ? log.Substring(log.Length - 600) : log;
        }

        /// <summary>One argument as the C runtime splits a command line (ArgumentList isn't in netstandard2.1).</summary>
        private static string Quote(string arg)
        {
            if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
                return arg;
            var quoted = new StringBuilder("\"");
            var slashes = 0;
            foreach (var c in arg)
            {
                if (c == '\\')
                {
                    slashes++;
                    continue;
                }
                quoted.Append('\\', c == '"' ? slashes * 2 + 1 : slashes).Append(c);
                slashes = 0;
            }
            return quoted.Append('\\', slashes * 2).Append('"').ToString();
        }

        private static string NewToken()
        {
            var bytes = new byte[18];
            using (var rng = RandomNumberGenerator.Create())
                rng.GetBytes(bytes);
            return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant();
        }
    }
}
