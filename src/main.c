#include <stdio.h>
#include "utils.h"

struct Person {
    char* name;
    int age;
};

void greet(struct Person* p) {
    printf("Hello, %s!\n", p->name);
}

int main() {
    struct Person person = {"Alice", 25};
    greet(&person);
    int sum = add(5, 3);
    printf("Sum: %d\n", sum);
    return 0;
} 