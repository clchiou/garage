package nng;

import static nng.Error.check;
import static nng.Nng.NNG;

/**
 * Higher-level representation of protocols.
 */
public enum Protocols {
    BUS0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_bus0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_bus0_open_raw(socket));
        }
    },

    PAIR0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_pair0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_pair0_open_raw(socket));
        }
    },
    PAIR1 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_pair1_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_pair1_open_raw(socket));
        }
    },

    PULL0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_pull0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_pull0_open_raw(socket));
        }
    },
    PUSH0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_push0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_push0_open_raw(socket));
        }
    },

    PUB0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_pub0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_pub0_open_raw(socket));
        }
    },
    SUB0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_sub0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_sub0_open_raw(socket));
        }
    },

    REP0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_rep0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_rep0_open_raw(socket));
        }
    },
    REQ0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_req0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_req0_open_raw(socket));
        }
    },

    RESPONDENT0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_respondent0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_respondent0_open_raw(socket));
        }
    },
    SURVEYOR0 {
        @Override
        void open(nng_socket socket) {
            check(NNG.nng_surveyor0_open(socket));
        }

        @Override
        void openRaw(nng_socket socket) {
            check(NNG.nng_surveyor0_open_raw(socket));
        }
    };

    /* package private */
    abstract void open(nng_socket socket);

    /* package private */
    abstract void openRaw(nng_socket socket);
}
