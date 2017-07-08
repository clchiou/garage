package nanomsg;

import com.google.common.base.Preconditions;
import com.google.common.collect.ImmutableSet;
import com.google.common.collect.Sets;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

public enum Option {

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
    NN_WS_MSG_TYPE(symbol("NN_WS_MSG_TYPE"));

    // Consult nn_setsockopt API doc for the list of writable options.
    static final ImmutableSet<Option> WRITABLE = Sets.immutableEnumSet(

        // Writable socket option.
        NN_SNDBUF,
        NN_RCVBUF,
        NN_RCVMAXSIZE,
        NN_SNDTIMEO,
        NN_RCVTIMEO,
        NN_RECONNECT_IVL,
        NN_RECONNECT_IVL_MAX,
        NN_SNDPRIO,
        NN_RCVPRIO,
        NN_IPV4ONLY,
        NN_SOCKET_NAME,
        NN_MAXTTL,
        NN_LINGER,

        // Writable transport option.
        NN_SUB_SUBSCRIBE,
        NN_SUB_UNSUBSCRIBE,
        NN_REQ_RESEND_IVL,
        NN_SURVEYOR_DEADLINE,
        NN_TCP_NODELAY,
        NN_WS_MSG_TYPE
    );

    public enum Type {

        NN_TYPE_NONE(symbol("NN_TYPE_NONE")),
        NN_TYPE_INT(symbol("NN_TYPE_INT")),
        NN_TYPE_STR(symbol("NN_TYPE_STR"));

        final int value;

        Type(nn_symbol_properties props) {
            Preconditions.checkArgument(
                props.ns == Namespace.NN_NS_OPTION_TYPE.value);
            value = props.value;
        }

        // This is only called during class load; so it is probably fine
        // that we do a linear search here.
        static Type byValue(int value) {
            for (Type type : values()) {
                if (type.value == value) {
                    return type;
                }
            }
            throw new AssertionError();
        }
    }

    public enum Unit {

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

        // This is only called during class load; so it is probably fine
        // that we do a linear search here.
        static Unit byValue(int value) {
            for (Unit unit : values()) {
                if (unit.value == value) {
                    return unit;
                }
            }
            throw new AssertionError();
        }
    }

    final Type type;
    final Unit unit;

    final int value;

    Option(nn_symbol_properties props) {
        Preconditions.checkArgument(
            props.ns == Namespace.NN_NS_SOCKET_OPTION.value ||
            props.ns == Namespace.NN_NS_TRANSPORT_OPTION.value
        );
        type = Type.byValue(props.type);
        unit = Unit.byValue(props.unit);
        value = props.value;
    }
}
