#ifndef TASK_H
#define TASK_H

#include <string>

class Task {
private:
    int id;
    std::string title;
    int priority;

public:
    Task(int id, std::string title, int priority);

    int getId() const;
    std::string getTitle() const;
    int getPriority() const;
};

#endif