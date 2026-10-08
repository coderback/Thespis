#nullable enable

namespace Thespis
{
    /// <summary>
    /// The outcome of a Thespis call. A call never throws for a failure the game should handle (a server that's
    /// away, an unknown NPC, a cap): it returns a result, and the game decides.
    /// <code>
    /// var r = await thespis.DecideAsync("garrick", "turn");
    /// if (r.Ok) Show(r.Value); else Debug.LogWarning(r);
    /// </code>
    /// </summary>
    public sealed class Result<T>
    {
        public bool Ok { get; }
        /// <summary>The reply, typed; default when the call failed.</summary>
        public T? Value { get; }
        /// <summary>The server's code (not_found, not_allowed, over_cap...), or unreachable, bad_reply.</summary>
        public string Error { get; }
        /// <summary>What went wrong, in words.</summary>
        public string Reason { get; }
        /// <summary>The HTTP status; 0 when the server was never reached.</summary>
        public int Status { get; }

        private Result(bool ok, T? value, string error, string reason, int status)
        {
            Ok = ok;
            Value = value;
            Error = error;
            Reason = reason;
            Status = status;
        }

        public static Result<T> Success(T value, int status = 200) => new Result<T>(true, value, "", "", status);

        public static Result<T> Failure(string error, string reason, int status = 0) =>
            new Result<T>(false, default, error, reason, status);

        /// <summary>The same failure, as a result of another type.</summary>
        public Result<TOther> As<TOther>() => Result<TOther>.Failure(Error, Reason, Status);

        public override string ToString() => Ok ? $"ok {Value}" : $"{Error} ({Status}): {Reason}";
    }
}
