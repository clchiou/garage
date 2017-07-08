package nanomsg;

import com.google.common.base.Preconditions;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

/**
 * The rest of the symbols.
 *
 * We might later move subset of symbols into their own enum class, like
 * we did for Domain, but for now, let's just lump together all of them
 * here.
 */
public enum Symbol {

    NN_VERSION_CURRENT(symbol("NN_VERSION_CURRENT")),
    NN_VERSION_REVISION(symbol("NN_VERSION_REVISION")),
    NN_VERSION_AGE(symbol("NN_VERSION_AGE")),

    NN_INPROC(symbol("NN_INPROC")),
    NN_IPC(symbol("NN_IPC")),
    NN_TCP(symbol("NN_TCP")),
    NN_WS(symbol("NN_WS")),

    NN_SOCKADDR_MAX(symbol("NN_SOCKADDR_MAX")),

    NN_SOL_SOCKET(symbol("NN_SOL_SOCKET")),

    NN_DONTWAIT(symbol("NN_DONTWAIT")),
    NN_WS_MSG_TYPE_TEXT(symbol("NN_WS_MSG_TYPE_TEXT")),
    NN_WS_MSG_TYPE_BINARY(symbol("NN_WS_MSG_TYPE_BINARY")),

    NN_POLLIN(symbol("NN_POLLIN")),
    NN_POLLOUT(symbol("NN_POLLOUT")),

    EADDRINUSE(symbol("EADDRINUSE")),
    EADDRNOTAVAIL(symbol("EADDRNOTAVAIL")),
    EAFNOSUPPORT(symbol("EAFNOSUPPORT")),
    EAGAIN(symbol("EAGAIN")),
    EBADF(symbol("EBADF")),
    ECONNREFUSED(symbol("ECONNREFUSED")),
    EFAULT(symbol("EFAULT")),
    EFSM(symbol("EFSM")),
    EINPROGRESS(symbol("EINPROGRESS")),
    EINTR(symbol("EINTR")),
    EINVAL(symbol("EINVAL")),
    EMFILE(symbol("EMFILE")),
    ENAMETOOLONG(symbol("ENAMETOOLONG")),
    ENETDOWN(symbol("ENETDOWN")),
    ENOBUFS(symbol("ENOBUFS")),
    ENODEV(symbol("ENODEV")),
    ENOMEM(symbol("ENOMEM")),
    ENOPROTOOPT(symbol("ENOPROTOOPT")),
    ENOTSOCK(symbol("ENOTSOCK")),
    ENOTSUP(symbol("ENOTSUP")),
    EPROTO(symbol("EPROTO")),
    EPROTONOSUPPORT(symbol("EPROTONOSUPPORT")),
    ETERM(symbol("ETERM")),
    ETIMEDOUT(symbol("ETIMEDOUT")),
    EACCES(symbol("EACCES")),
    ECONNABORTED(symbol("ECONNABORTED")),
    ECONNRESET(symbol("ECONNRESET")),
    EHOSTUNREACH(symbol("EHOSTUNREACH")),
    EMSGSIZE(symbol("EMSGSIZE")),
    ENETRESET(symbol("ENETRESET")),
    ENETUNREACH(symbol("ENETUNREACH")),
    ENOTCONN(symbol("ENOTCONN"));

    /*
     * Symbol metadata.
     */

    // Metadata.
    public final Namespace namespace;

    // Symbol value.
    public final int value;

    Symbol(nn_symbol_properties props) {
        Preconditions.checkArgument(
            Option.Type.byValue(props.type) == Option.Type.NN_TYPE_NONE);
        Preconditions.checkArgument(
            Option.Unit.byValue(props.unit) == Option.Unit.NN_UNIT_NONE);
        namespace = Namespace.byValue(props.ns);
        value = props.value;
    }

    @Override
    public String toString() {
        return String.format("%s<%s, %d>", name(), namespace.name(), value);
    }
}
