#include "Task.h"

Task::Task(int id, std::string title, int priority) {
    this->id = id;
    this->title = title;
    this->priority = priority;
}

int Task::getId() const {
    return id;
}

std::string Task::getTitle() const {
    return title;
}

int Task::getPriority() const {
    return priority;
}