#include "lib/base.h"
#include "lib/list.h"


static void list_insert_item(struct list *self, struct list *other);
static void list_remove_item(struct list *self);


void list_insert(struct list **head, struct list *self)
{
	if (*head)
		list_insert_item(*head, self);
	*head = self;
}


void list_remove(struct list **head, struct list *self)
{
	list_remove_item(self);
	if (*head == self)
		*head = self->next;
}


static void list_insert_item(struct list *self, struct list *other)
{
	expect(self && other);

	other->prev = self->prev;
	other->next = self;
	self->prev = other;
}


static void list_remove_item(struct list *self)
{
	expect(self);

	if (self->prev)
		self->prev->next = self->next;
	if (self->next)
		self->next->prev = self->prev;
}
