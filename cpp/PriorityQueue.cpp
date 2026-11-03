#include <iostream>
#include <queue>
#include <vector>
#include <string>

using namespace std;

struct Task {
    int id;
    string title;
    int priority;
};

struct CompareTask {
    bool operator()(const Task& a, const Task& b) {
        return a.priority < b.priority;
    }
};

int main() {
    priority_queue<
        Task,
        vector<Task>,
        CompareTask
    > taskQueue;

    taskQueue.push({1, "Database Backup", 3});
    taskQueue.push({2, "Payment Processing", 9});
    taskQueue.push({3, "Email Notification", 5});

    while (!taskQueue.empty()) {
        Task current = taskQueue.top();
        taskQueue.pop();

        cout << "Task ID: " << current.id
             << " | Title: " << current.title
             << " | Priority: " << current.priority
             << endl;
    }

    return 0;
}