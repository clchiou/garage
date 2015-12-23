#ifndef HASH_TABLE_
#define HASH_TABLE_

#include <stdbool.h>
#include <stdint.h>

#include "lib/list.h"
#include "lib/view.h"

typedef size_t (*hash_func)(struct ro_view key);

struct hash_table {
	hash_func hash_func;
	size_t size;
	struct list *table[];
};

struct hash_table_entry {
	struct ro_view key;
	struct rw_view value;
	struct list list;
};

void hash_table_init(struct hash_table *table, hash_func hash_func, size_t size);

bool hash_table_has(struct hash_table *table, struct ro_view key);

struct rw_view hash_table_get(struct hash_table *table, struct ro_view key);

bool hash_table_put(struct hash_table *table,
		struct hash_table_entry *new_entry,
		struct hash_table_entry *old_entry);

bool hash_table_pop(struct hash_table *table,
		struct ro_view key,
		struct hash_table_entry *old_entry);

#endif
