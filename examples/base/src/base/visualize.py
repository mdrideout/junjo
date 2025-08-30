from base.sample_workflow.graph import create_sample_workflow_graph


def main():
    """
    Demonstration visualization options for the sample workflow graph.
    """
    graph_dot_notation_str = create_sample_workflow_graph().to_dot_notation()
    print("Graph DOT Notation:\n", graph_dot_notation_str)

    # Export graphviz assets
    create_sample_workflow_graph().export_graphviz_assets()


if __name__ == "__main__":
    main()
