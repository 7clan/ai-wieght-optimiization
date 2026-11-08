window.Sidebar = function Sidebar(props) {
  return (
    <div className={'sidebar' + (props.sidebarOpen ? ' open' : '')}>
      <h3 className="sidebar-label">PROJECTS</h3>
      <ul>
        {props.projects.map((project, index) => (
          <li key={index} className="nav-item">
            <button className={'nav-item' + (project.id === props.activeId ? ' active' : '')} onClick={() => props.onSelect(project.id)}>
              {project.name}
              <span className="badge">{props.counts[project.id] || 0}</span>
            </button>
          </li>
        ))}
      </ul>
      <button className="btn btn-ghost btn-block" onClick={() => props.onNewProject()}>
        + New Project
      </button>
    </div>
  );
};
