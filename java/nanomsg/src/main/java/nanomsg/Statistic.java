package nanomsg;

import com.google.common.base.Preconditions;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

public enum Statistic {

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

    final int value;

    Statistic(nn_symbol_properties props) {
        Preconditions.checkArgument(
            props.ns == Namespace.NN_NS_STATISTIC.value);
        value = props.value;
    }
}
