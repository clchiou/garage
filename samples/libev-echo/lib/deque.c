#include "base.h"
#include "deque.h"


void deque_enque(struct deque **head, struct deque *self)
{
	if (*head)
		deque_insert(*head, self);
	*head = self;
}


void deque_deque(struct deque **head, struct deque *self)
{
	deque_remove(self);
	if (*head == self)
		*head = self->next;
}


void deque_insert(struct deque *self, struct deque *other)
{
	expect(self && other);

	other->prev = self->prev;
	other->next = self;
	self->prev = other;
}


void deque_remove(struct deque *self)
{
	expect(self);

	if (self->prev)
		self->prev->next = self->next;
	if (self->next)
		self->next->prev = self->prev;
}
