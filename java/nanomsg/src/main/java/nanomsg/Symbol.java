package nanomsg;

import com.google.common.base.Preconditions;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

public enum Symbol {

    NN_VERSION_CURRENT(symbol("NN_VERSION_CURRENT")),
    NN_VERSION_REVISION(symbol("NN_VERSION_REVISION")),
    NN_VERSION_AGE(symbol("NN_VERSION_AGE")),

    AF_SP(symbol("AF_SP")),
    AF_SP_RAW(symbol("AF_SP_RAW")),

    NN_INPROC(symbol("NN_INPROC")),
    NN_IPC(symbol("NN_IPC")),
    NN_TCP(symbol("NN_TCP")),
    NN_WS(symbol("NN_WS")),

    NN_PAIR(symbol("NN_PAIR")),
    NN_PUB(symbol("NN_PUB")),
    NN_SUB(symbol("NN_SUB")),
    NN_REP(symbol("NN_REP")),
    NN_REQ(symbol("NN_REQ")),
    NN_PUSH(symbol("NN_PUSH")),
    NN_PULL(symbol("NN_PULL")),
    NN_SURVEYOR(symbol("NN_SURVEYOR")),
    NN_RESPONDENT(symbol("NN_RESPONDENT")),
    NN_BUS(symbol("NN_BUS")),

    NN_SOCKADDR_MAX(symbol("NN_SOCKADDR_MAX")),

    NN_SOL_SOCKET(symbol("NN_SOL_SOCKET")),

    NN_LINGER(symbol("NN_LINGER")),
    NN_SNDBUF(symbol("NN_SNDBUF")),
    NN_RCVBUF(symbol("NN_RCVBUF")),
    NN_RCVMAXSIZE(symbol("NN_RCVMAXSIZE")),
    NN_SNDTIMEO(symbol("NN_SNDTIMEO")),
    NN_RCVTIMEO(symbol("NN_RCVTIMEO")),
    NN_RECONNECT_IVL(symbol("NN_RECONNECT_IVL")),
    NN_RECONNECT_IVL_MAX(symbol("NN_RECONNECT_IVL_MAX")),
    NN_SNDPRIO(symbol("NN_SNDPRIO")),
    NN_RCVPRIO(symbol("NN_RCVPRIO")),
    NN_SNDFD(symbol("NN_SNDFD")),
    NN_RCVFD(symbol("NN_RCVFD")),
    NN_DOMAIN(symbol("NN_DOMAIN")),
    NN_PROTOCOL(symbol("NN_PROTOCOL")),
    NN_IPV4ONLY(symbol("NN_IPV4ONLY")),
    NN_SOCKET_NAME(symbol("NN_SOCKET_NAME")),
    NN_MAXTTL(symbol("NN_MAXTTL")),

    NN_SUB_SUBSCRIBE(symbol("NN_SUB_SUBSCRIBE")),
    NN_SUB_UNSUBSCRIBE(symbol("NN_SUB_UNSUBSCRIBE")),
    NN_REQ_RESEND_IVL(symbol("NN_REQ_RESEND_IVL")),
    NN_SURVEYOR_DEADLINE(symbol("NN_SURVEYOR_DEADLINE")),
    NN_TCP_NODELAY(symbol("NN_TCP_NODELAY")),
    NN_WS_MSG_TYPE(symbol("NN_WS_MSG_TYPE")),

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
    ENOTCONN(symbol("ENOTCONN")),

    NN_STAT_ESTABLISHED_CONNECTIONS(symbol("NN_STAT_ESTABLISHED_CONNECTIONS")),
    NN_STAT_ACCEPTED_CONNECTIONS(symbol("NN_STAT_ACCEPTED_CONNECTIONS")),
    NN_STAT_DROPPED_CONNECTIONS(symbol("NN_STAT_DROPPED_CONNECTIONS")),
    NN_STAT_BROKEN_CONNECTIONS(symbol("NN_STAT_BROKEN_CONNECTIONS")),
    NN_STAT_CONNECT_ERRORS(symbol("NN_STAT_CONNECT_ERRORS")),
    NN_STAT_BIND_ERRORS(symbol("NN_STAT_BIND_ERRORS")),
    NN_STAT_ACCEPT_ERRORS(symbol("NN_STAT_ACCEPT_ERRORS")),
    NN_STAT_MESSAGES_SENT(symbol("NN_STAT_MESSAGES_SENT")),
    NN_STAT_MESSAGES_RECEIVED(symbol("NN_STAT_MESSAGES_RECEIVED")),
    NN_STAT_BYTES_SENT(symbol("NN_STAT_BYTES_SENT")),
    NN_STAT_BYTES_RECEIVED(symbol("NN_STAT_BYTES_RECEIVED")),
    NN_STAT_CURRENT_CONNECTIONS(symbol("NN_STAT_CURRENT_CONNECTIONS")),
    NN_STAT_INPROGRESS_CONNECTIONS(symbol("NN_STAT_INPROGRESS_CONNECTIONS")),
    NN_STAT_CURRENT_SND_PRIORITY(symbol("NN_STAT_CURRENT_SND_PRIORITY")),
    NN_STAT_CURRENT_EP_ERRORS(symbol("NN_STAT_CURRENT_EP_ERRORS"));

    /*
     * Symbol metadata.
     */

    public static enum Namespace {

        NN_NS_NAMESPACE(symbol("NN_NS_NAMESPACE")),
        NN_NS_VERSION(symbol("NN_NS_VERSION")),
        NN_NS_DOMAIN(symbol("NN_NS_DOMAIN")),
        NN_NS_TRANSPORT(symbol("NN_NS_TRANSPORT")),
        NN_NS_PROTOCOL(symbol("NN_NS_PROTOCOL")),
        NN_NS_OPTION_LEVEL(symbol("NN_NS_OPTION_LEVEL")),
        NN_NS_SOCKET_OPTION(symbol("NN_NS_SOCKET_OPTION")),
        NN_NS_TRANSPORT_OPTION(symbol("NN_NS_TRANSPORT_OPTION")),
        NN_NS_OPTION_TYPE(symbol("NN_NS_OPTION_TYPE")),
        NN_NS_OPTION_UNIT(symbol("NN_NS_OPTION_UNIT")),
        NN_NS_FLAG(symbol("NN_NS_FLAG")),
        NN_NS_ERROR(symbol("NN_NS_ERROR")),
        NN_NS_LIMIT(symbol("NN_NS_LIMIT")),
        NN_NS_EVENT(symbol("NN_NS_EVENT")),
        NN_NS_STATISTIC(symbol("NN_NS_STATISTIC"));

        final int value;

        Namespace(nn_symbol_properties props) {
            Preconditions.checkArgument(props.ns == 0);
            value = props.value;
        }

        // This is only called during class load; so it is probably fine
        // that we do a linear search here.
        private static Namespace byValue(int value) {
            for (Namespace namespace : values()) {
                if (namespace.value == value) {
                    return namespace;
                }
            }
            throw new AssertionError();
        }
    }

    public static enum Type {

        NN_TYPE_NONE(symbol("NN_TYPE_NONE")),
        NN_TYPE_INT(symbol("NN_TYPE_INT")),
        NN_TYPE_STR(symbol("NN_TYPE_STR"));

        final int value;

        Type(nn_symbol_properties props) {
            Preconditions.checkArgument(
                props.ns == Namespace.NN_NS_OPTION_TYPE.value);
            value = props.value;
        }

        // Same as above.
        private static Type byValue(int value) {
            for (Type type : values()) {
                if (type.value == value) {
                    return type;
                }
            }
            throw new AssertionError();
        }
    }

    public static enum Unit {

        NN_UNIT_NONE(symbol("NN_UNIT_NONE")),
        NN_UNIT_BYTES(symbol("NN_UNIT_BYTES")),
        NN_UNIT_MILLISECONDS(symbol("NN_UNIT_MILLISECONDS")),
        NN_UNIT_PRIORITY(symbol("NN_UNIT_PRIORITY")),
        NN_UNIT_BOOLEAN(symbol("NN_UNIT_BOOLEAN")),
        NN_UNIT_MESSAGES(symbol("NN_UNIT_MESSAGES")),
        NN_UNIT_COUNTER(symbol("NN_UNIT_COUNTER"));

        final int value;

        Unit(nn_symbol_properties props) {
            Preconditions.checkArgument(
                props.ns == Namespace.NN_NS_OPTION_UNIT.value);
            value = props.value;
        }

        // Same as above.
        private static Unit byValue(int value) {
            for (Unit unit : values()) {
                if (unit.value == value) {
                    return unit;
                }
            }
            throw new AssertionError();
        }
    }

    public final Namespace namespace;
    public final Type type;
    public final Unit unit;

    public final String name;
    public final int value;

    Symbol(nn_symbol_properties props) {
        namespace = Namespace.byValue(props.ns);
        type = Type.byValue(props.type);
        unit = Unit.byValue(props.unit);
        name = props.name;
        value = props.value;
    }

    @Override
    public String toString() {
        return String.format(
            "%s<%s, %s, %s, %d>",
            name, namespace.name(), type.name(), unit.name(), value
        );
    }
}
