DROP TABLE IF EXISTS `books`;
DROP TABLE IF EXISTS `authors`;

CREATE TABLE `books` (
    `id` INT PRIMARY KEY NOT NULL,
    -- For convenience, we assume there is only single author.
    `author_id` INT NOT NULL REFERENCES `authors` (`id`),
    `title` TEXT NOT NULL
);

CREATE TABLE `authors` (
    `id` INT PRIMARY KEY NOT NULL,
    `name` TEXT NOT NULL
);

-- Also create some test data.

INSERT INTO `books` (`id`, `author_id`, `title`) VALUES
    (1, 1, "Ulysses"),
    (2, 2, "The Great Gatsby"),
    (3, 1, "A Portrait of the Artist as a Young Man"),
    (4, 3, "Lolita"),
    (5, 4, "Brave New World"),
    (6, 5, "The Sound and the Fury"),
    (7, 6, "Catch-22"),
    (8, 7, "Darkness at Noon"),
    (9, 8, "Sons and Lovers"),
    (10, 9, "The Grapes of Wrath");

INSERT INTO `authors` (`id`, `name`) VALUES
    (1, "James Joyce"),
    (2, "F. Scott Fitzgerald"),
    (3, "Vladimir Nabokov"),
    (4, "Aldous Huxley"),
    (5, "William Faulkner"),
    (6, "Joseph Heller"),
    (7, "Arthur Koestler"),
    (8, "D. H. Lawrence"),
    (9, "John Steinbeck");
