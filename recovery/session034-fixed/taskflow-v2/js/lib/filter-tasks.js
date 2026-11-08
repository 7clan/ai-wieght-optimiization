// Define the filterTasks function
window.filterTasks = function filterTasks(tasks, query, filter) {
  // Convert query to lowercase for case-insensitive comparison
  const lowerQuery = query.toLowerCase();
  
  // Filter tasks based on title and status
  return tasks.filter(task => {
    // Check if title contains the query
    if (task.title.toLowerCase().includes(lowerQuery)) {
      // Check if status is 'all' or the task's status matches the filter
      return filter === 'all' || task.status === filter;
    }
    
    // Return false if no match is found
    return false;
  });
};
