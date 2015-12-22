#ifndef LIST_H_
#define LIST_H_

struct list {
	struct list *prev, *next;
};

void list_insert(struct list **head, struct list *self);

void list_remove(struct list **head, struct list *self);

#endif
