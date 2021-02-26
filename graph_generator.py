from classes import Vertex, Edge, Graph, Law, Section, WrapUp, Appendix
from db_handler import init_graph
from datetime import datetime
import csv

from db_handler_rdf import init_db
from utils import classify_tag, classify_vertex_by_tag_and_eid, get_ref_ancestor_element, build_laws_mapping, \
    parse_ref, classify_eid_by_tag, search_ref_ancestor_element
from error import write_to_errors_file, init_errors_dict
from constants import HREF, EdgeType
import pickle

import logging

logging.basicConfig(filename='law_graph_logs.log', level=logging.INFO)
# logging.basicConfig(level=logging.INFO)


def get_from_vertex(from_law, ref_element, edges, vertexes_map):
    """ Searches for a to_vertex
    1. Searches for the first ancestor of the element to be the from_vertex
    2. Sets up an inner (law and an element in it) edge: from_law => from_vertex

    """
    from_vertex: Vertex = get_ref_ancestor_element(law=from_law, element=ref_element, vertexes_map=vertexes_map)
    # try:
    #     from_vertex_p: Vertex = search_ref_ancestor_element(
    #         law=from_law, element=from_vertex.element, vertexes_map=vertexes_map)
    #     while True:
    #         if hash(from_vertex_p) in vertexes_map:
    #             from_vertex_p = vertexes_map[hash(from_vertex_p)]
    #             break
    #         else:
    #             from_vertex_p: Vertex = search_ref_ancestor_element(
    #                 law=from_law, element=from_vertex_p.element, vertexes_map=vertexes_map)
    #     filter_by_ends = list(filter(lambda e: e.to_vertex == from_vertex_p and e.from_vertex == from_vertex, edges))
    #     if len(filter_by_ends) == 0:
    #         setup_inner_edge(from_vertex, from_vertex_p, edges)  # setup an inner edge from_law => from_vertex
    # except FileNotFoundError:
    #     pass
    setup_inner_edge(from_law, from_vertex, edges)

    setup_inner_edge(from_vertex, from_law, edges)  # setup an inner edge from_law => from_vertex
    return from_vertex


def get_to_vertex(from_law, ref_element, errors_dict, frbr_work_uri_to_law, edges, vertexes_map):
    """ Searches for a from_vertex
    1. Parse the reference text to get frbr_work_uri prefix and element identifier (eid)
    2. Classify the vertex's tag by the eid
    3. Classify potential eids
    4. Get the to_vertex using it's tag and eid
    5. Sets up an inner (law and an element in it) edge: to_law => to_vertex

    """
    frbr_work_uri, eid = parse_ref(ref_element=ref_element, from_law=from_law, errors_dict=errors_dict)
    if not frbr_work_uri:
        return from_law

    to_law: Law = frbr_work_uri_to_law[frbr_work_uri]
    tag: str = classify_tag(eid=eid, errors_dict=errors_dict, from_law=from_law, ref_element=ref_element)
    eids: list = classify_eid_by_tag(tag=tag, eid=eid)
    to_vertex: Vertex = classify_vertex_by_tag_and_eid(
        tag=tag, eids=eids, to_law=to_law, errors_dict=errors_dict, from_law=from_law, from_element=ref_element,
        vertexes_map=vertexes_map
    )
    # if type(to_vertex) is not Law:
    #     try:
    #         to_vertex_p: Vertex = search_ref_ancestor_element(
    #             law=from_law, element=to_vertex.element, vertexes_map=vertexes_map)
    #         while True:
    #             if hash(to_vertex_p) in vertexes_map:
    #                 to_vertex_p = vertexes_map[hash(to_vertex_p)]
    #                 break
    #             else:
    #                 to_vertex_p: Vertex = search_ref_ancestor_element(
    #                     law=from_law, element=to_vertex_p.element, vertexes_map=vertexes_map)
    #         setup_inner_edge(to_vertex, to_vertex_p, edges)  # setup an inner edge from_law => to_vertex
    #     except FileNotFoundError:
    #         pass
    # if to_vertex != to_law:
    setup_inner_edge(to_vertex, to_law, edges)  # setup an inner edge to_law => to_vertex
    setup_inner_edge(to_law, to_vertex, edges)

    return to_vertex


def setup_inner_edge(law, vertex, edges):
    """ Sets up an inner (law and an element in it) edge """
    inner_edge = Edge(law, vertex, vertex.element)
    edges.add(inner_edge)
    vertex.add_in_edge(inner_edge)
    law.add_out_edge(inner_edge)


def generate_graph():
    """ Generate the graph """
    edges: set = set()
    total_refs: int = 0
    successful_refs: int = 0
    errors_dict = init_errors_dict()
    laws, frbr_work_uri_to_law = build_laws_mapping()
    vertexes_map = {hash(law): law for law in laws}

    for from_law in laws:
        law_edges: set = set()
        for ref_element in from_law.get_ref_elements():
            from_vertex: Vertex = get_from_vertex(from_law, ref_element, law_edges, vertexes_map)

            to_vertex: Vertex = get_to_vertex(
                from_law, ref_element, errors_dict, frbr_work_uri_to_law, law_edges, vertexes_map
            )
            if not to_vertex:
                total_refs += 1
                continue

            # setup an edge and maintain metadata
            edge: Edge = Edge(from_vertex, to_vertex, ref_element)
            law_edges.add(edge)
            from_vertex.add_out_edge(edge)
            to_vertex.add_in_edge(edge)

            successful_refs += 1
            total_refs += 1
            logging.info(f"{total_refs}. Succeed to handle href {ref_element.attrib[HREF]} in from_law {from_law.path}")

        edges.update(law_edges)

    logging.info(f'{total_refs = }, {successful_refs = }, failed_not_handled_refs = {total_refs - successful_refs}')
    write_to_errors_file(errors_dict)

    edges_cleaned = clean_edges(edges)
    # return Graph(set(vertexes_map.values()), edges)
    return Graph(set(vertexes_map.values()), edges_cleaned)


def get_isolated_subgraphs(edges: set[Edge], law: Law):
    checked_nodes: set[Vertex] = set()
    subgraphs = list()
    for edge in edges:
        node = edge.from_vertex
        subgraph = set()
        find_subgraph(node, checked_nodes, subgraph)
        if len(subgraph) != 0:
            if law not in subgraph:
                subgraphs.append(subgraph)

    return subgraphs


def find_subgraph(node: Vertex, checked_nodes: set[Vertex], subgraph: set):
    if node in checked_nodes:
        return
    neighbors = get_neighbors(node)
    checked_nodes.add(node)
    subgraph.add(node)
    neighbors = neighbors - checked_nodes
    for n in neighbors:
        find_subgraph(n, checked_nodes, subgraph)
    return


def get_neighbors(node: Vertex):
    neighbors_in = set(filter(lambda e1: node.law.id == e1.law.id, map(lambda e: e.from_vertex, node.in_edges)))
    neighbors_out = set(filter(lambda e1: node.law.id == e1.law.id, map(lambda e: e.to_vertex, node.out_edges)))
    all_neighbors = neighbors_in.copy()
    all_neighbors.update(neighbors_out)
    return all_neighbors


def clean_edges(edges):
    no_generics = list(filter(lambda edge: edge.to_vertex.id != edge.from_vertex.id and edge.type != EdgeType.Generic,
                              edges))
    # no_extra_edges = list(filter(lambda edge:
    #                              len(edge.from_vertex.in_edges) == 0 or edge.type != EdgeType.Section_of_law,
    #                              no_generics))
    return no_generics


def main():
    try:
        graph = generate_graph()
        # init_db(graph)
        print("Finish Graph Time =", datetime.now().strftime("%H:%M:%S"))
        # init_graph(graph)

        with open('Nodes.csv', mode='w') as nodes_file:
            nodes_writer = csv.writer(nodes_file, delimiter='¡', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            nodes_writer.writerow([':ID', ':LABEL', 'title', 'body', 'law_uri:string'])
            for v in graph.V:
                nodes_writer.writerow([v.id, type(v).__name__, v.title, v.body, v.law.path])

        with open('Edges.csv', mode='w') as edges_file:
            edges_writer = csv.writer(edges_file, delimiter='¡', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            edges_writer.writerow([':START_ID', ':TYPE', ':END_ID'])
            for e in graph.E:
                edges_writer.writerow([e.from_vertex.id, e.type, e.to_vertex.id])

        print('Vertexes = ', len(graph.V))
        print('Edges = ', len(graph.E))

        print("End Time =", datetime.now().strftime("%H:%M:%S"))

    except Exception as e:
        logging.exception(str(e), exc_info=True)
        raise e


if __name__ == '__main__':
    # @TODO: add all laws to the vertexes

    print("Start Time =", datetime.now().strftime("%H:%M:%S"))
    main()
