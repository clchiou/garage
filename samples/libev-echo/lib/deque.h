#ifndef DEQUE_H_
#define DEQUE_H_

struct deque {
	struct deque *prev, *next;
};

void deque_enque(struct deque **head, struct deque *self);

void deque_deque(struct deque **head, struct deque *self);

void deque_insert(struct deque *self, struct deque *other);

void deque_remove(struct deque *self);

#endif
