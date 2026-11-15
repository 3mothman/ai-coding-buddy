#include <stdio.h>

int main(void) {
    int values[] = {4, -2, 9, 3};
    int maximum = values[0];
    for (int i = 1; i < 4; ++i) {
        if (values[i] > maximum) {
            maximum = values[i];
        }
    }
    printf("%d\n", maximum);
    return 0;
}
