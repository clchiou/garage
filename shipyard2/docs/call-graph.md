#### Call graph of image release process

    +---------------+
    | release       |
    +-------+-------+
            |
            V
    +-------+-------+
    | foreman       |
    +-------+-------+
            | (Through rules/images/...)
            V
    +-------+-------+
    | ctr           |
    +-------+-------+
            |
            V
    +-------+-------+
    | builder pod   |
    | +-----------+ |
    | | foreman   | |
    | +-----------+ |
    +---------------+
