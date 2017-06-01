DROP TABLE IF EXISTS `books`;
CREATE TABLE `books` (
    `id` INT PRIMARY KEY NOT NULL,
    `title` TEXT NOT NULL
);

DROP TABLE IF EXISTS `authors`;
CREATE TABLE `authors` (
    `id` INT PRIMARY KEY NOT NULL,
    `name` TEXT NOT NULL
);

DROP TABLE IF EXISTS `books_authors`;
CREATE TABLE `books_authors` (
    `book_id` INT NOT NULL REFERENCES `books` (`id`),
    `author_id` INT NOT NULL REFERENCES `authors` (`id`),
    CONSTRAINT `unique_ids` UNIQUE (`book_id`, `author_id`)
);
